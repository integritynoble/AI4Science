"""Encoding models of language cortex — the interface, and the refusal.

**There is no brain-recording corpus on this machine.** Not a missing download,
not a stale path: nothing here has ever read one. What this module contains is
the INTERFACE a corpus must satisfy before the benchmark will compute anything,
and the machinery that refuses until one does.

That is deliberate, and it is the honest half of the work. The alternative —
simulating responses so the pipeline "runs" — produces a correlation that looks
like a result and describes a random-number generator, and nothing downstream
can tell the difference afterwards. So `load_corpus` raises, and every number
the benchmark reports is downstream of that raise.

Candidate public datasets, as COMMENTED POSSIBILITIES only:

    # Narratives (OpenNeuro ds002345) — fMRI, spoken stories, many subjects,
    #   some stimuli presented to the same subject more than once.
    # LeBel et al. 2023 (OpenNeuro ds003020) — fMRI, ~20 hours per subject of
    #   spoken narrative, with a repeated held-out story.
    # Pereira et al. 2018 — fMRI, sentences and passages.
    # ZuCo 1.0/2.0 — EEG with simultaneous eye tracking, read sentences.

Their schemas are **NOT asserted here**. Not one of those names has been opened
on this machine, and writing a loader against a layout nobody has looked at
produces a parser that fails in a way that reads like missing data. `INTERFACE`
below states what this benchmark needs; mapping any particular dataset onto it
is a person's job, done with the files in front of them, and it ends with a
`Corpus` whose `required` names files that actually exist.

The other seven corpora carry a `fetch` command. This one carries an empty
string on purpose: every candidate above requires a person to accept terms, and
`needs_agreement` already says that an agent may not accept them on anyone's
behalf. A fetcher here would be a fetcher for a dataset nobody has agreed to.

Refusal itself is not reimplemented. `corpus.Corpus.require` already produces
the actionable message — which corpus, which directory, which files — and a
second quieter style would be a second thing to audit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from . import corpus

#: The dataset this benchmark needs, described so it can be recognised.
#:
#: NOT registered in `corpus.ALL`. That dict is the set of corpora this machine
#: knows how to obtain, and this is a specification rather than an obtainable
#: thing; adding it there would put a key in `status()` that no fetcher can ever
#: clear. Registration is the owner's call, once a real dataset is chosen.
BRAIN_LANGUAGE = corpus.Corpus(
    key="brain-language",
    title="Brain responses to natural language, with repeated presentations",
    required=("responses.npz", "stimulus.json", "subjects.json", "metadata.json"),
    source="not chosen — see the module docstring for candidates and INTERFACE "
           "for what any of them must be mapped onto",
    licence="unknown until a dataset is chosen; every candidate known here is "
            "released under a data use agreement",
    # A DUA is accepted by a person, never by an agent.
    needs_agreement=True,
    # Empty on purpose: no fetcher exists, and one that clicked through an
    # agreement would be the thing this flag exists to prevent.
    fetch="",
    approx_size="unknown until a dataset is chosen",
)


#: What the four required files must contain, stated in code rather than prose.
#:
#: Shapes and not just field names. Every other runner here reads data whose
#: axes are implied by whichever generator wrote it, which works exactly as long
#: as one person holds both ends: the moment a corpus is prepared by someone
#: else, the arrays load, the axes are transposed, and the correlation is
#: computed across units instead of windows. A transposed matrix produces a
#: number, not an error, so the shape is half the contract.
INTERFACE = """\
brain-language — required layout under <root>/brain-language/

  responses.npz
      one array per subject, keyed by subject id:
          <subject>          shape (n_windows, n_units), float32
      plus, for the held-out material, repeated presentations:
          repeats/<subject>  shape (n_repeats, n_windows_heldout, n_units),
                             float32, with n_repeats >= 2
      n_units is per-subject and need not match across subjects; n_windows is
      shared and must. The repeated windows are the FINAL n_windows_heldout of
      the shared window sequence, so "which windows have a ceiling" is a fact
      about the corpus rather than a choice the benchmark gets to make.

  stimulus.json
      a list with exactly one entry per window, in window order:
          {"token": str or [str, ...], "onset_s": float, "offset_s": float}
      len(stimulus) == n_windows, and the entry order IS the row order.

  subjects.json
      a list of subject ids, matching the keys of responses.npz. This is the
      unit of the split: a train/test split cuts here and nowhere else.

  metadata.json
      {"sampling_rate_hz": float, "modality": str,
       "alignment": str}    -- the convention under which onsets were mapped to
                               response rows (e.g. haemodynamic lag applied, in
                               seconds), stated so a reader can check it.

THE ALIGNMENT GUARANTEE, which the rest of this module assumes everywhere:

  response row i of EVERY subject corresponds to stimulus window i, and the
  windows are SHARED across subjects. Subjects differ in n_units, never in
  n_windows and never in what row i means. A corpus that violates this scores a
  model against a different sentence than the one it was shown, and the result
  is a plausible-looking correlation with no interpretation at all.
"""


# --------------------------------------------------------------- the corpus

@dataclass(frozen=True)
class BrainCorpus:
    """A loaded corpus, with the alignment guarantee already checked."""

    root: Path
    #: subject id -> (n_windows, n_units)
    responses: Dict[str, np.ndarray]
    #: subject id -> (n_repeats, n_windows_heldout, n_units)
    repeats: Dict[str, np.ndarray]
    #: one entry per window, in row order
    stimulus: Tuple[Dict[str, Any], ...]
    subjects: Tuple[str, ...]
    metadata: Dict[str, Any]

    @property
    def n_windows(self) -> int:
        return len(self.stimulus)


def _check_alignment(responses: Dict[str, np.ndarray],
                     repeats: Dict[str, np.ndarray],
                     stimulus: Sequence[Any],
                     subjects: Sequence[str]) -> None:
    """Hold a loaded corpus to the guarantee INTERFACE states.

    Checked at load time rather than trusted, because every violation here is
    silent downstream: a transposed matrix still correlates, a short stimulus
    list still zips, and a subject missing from responses.npz just quietly
    stops being in the split. Each of those yields a number.
    """
    n_windows = len(stimulus)
    if n_windows < 2:
        raise ValueError("stimulus.json describes %d window(s); there is "
                         "nothing to correlate across" % n_windows)
    missing = [s for s in subjects if s not in responses]
    if missing:
        raise ValueError("subjects.json names %s, which responses.npz does not "
                         "contain" % ", ".join(sorted(missing)))
    for s in subjects:
        r = responses[s]
        if r.ndim != 2:
            raise ValueError("responses for %s have shape %r; INTERFACE "
                             "requires (n_windows, n_units)" % (s, r.shape))
        if r.shape[0] != n_windows:
            raise ValueError(
                "responses for %s have %d rows against %d stimulus windows. "
                "Either the windows are not shared across subjects or the "
                "matrix is transposed; both score a model against a sentence "
                "it was not shown." % (s, r.shape[0], n_windows))
    for s, rep in repeats.items():
        if rep.ndim != 3:
            raise ValueError("repeats/%s has shape %r; INTERFACE requires "
                             "(n_repeats, n_windows_heldout, n_units)"
                             % (s, rep.shape))
        if rep.shape[0] < 2:
            raise ValueError(
                "repeats/%s carries %d presentation(s). Below two there is no "
                "noise ceiling to measure, and this benchmark reports no "
                "correlation without one." % (s, rep.shape[0]))


def load_corpus(root: Optional[Path] = None) -> BrainCorpus:
    """The corpus, or an actionable refusal. Never a substitute for it.

    `require` raises `CorpusMissing` naming the directory searched and the files
    that were not in it. Nothing below that line has run on this machine, and
    that is the point: the loader exists so the interface is executable, not so
    the benchmark has something to fall back on.
    """
    d = BRAIN_LANGUAGE.require(root)
    stimulus = json.loads((d / "stimulus.json").read_text())
    subjects = [str(s) for s in json.loads((d / "subjects.json").read_text())]
    metadata = json.loads((d / "metadata.json").read_text())

    z = np.load(d / "responses.npz")
    responses = {k: np.asarray(z[k]) for k in z.files
                 if not k.startswith("repeats/")}
    repeats = {k[len("repeats/"):]: np.asarray(z[k]) for k in z.files
               if k.startswith("repeats/")}
    _check_alignment(responses, repeats, stimulus, subjects)
    return BrainCorpus(root=Path(d), responses=responses, repeats=repeats,
                       stimulus=tuple(stimulus), subjects=tuple(subjects),
                       metadata=metadata)


# ------------------------------------------------------------- the measures

def _column_pearson(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-column Pearson r between two (n_windows, n_units) matrices.

    A unit with no variance in either matrix scores 0 rather than being dropped.
    Dropping is the tempting version and it is wrong here: the floor, the
    ceiling and the candidate would each end up averaged over a different unit
    set, and the three numbers are only comparable — normalised against one
    another, subtracted from one another — while they describe the same units.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ac = a - a.mean(axis=0)
    bc = b - b.mean(axis=0)
    na = np.sqrt((ac * ac).sum(axis=0))
    nb = np.sqrt((bc * bc).sum(axis=0))
    live = (na > 0) & (nb > 0)
    r = np.zeros(a.shape[1], dtype=float)
    r[live] = (ac[:, live] * bc[:, live]).sum(axis=0) / (na[live] * nb[live])
    return r


def noise_ceiling(repeats: np.ndarray) -> float:
    """Split-half reliability across repeated presentations, Spearman-Brown
    corrected. The ceiling is MEASURED here, never assumed.

    `repeats` is (n_repeats, n_windows, n_units). The repeats are split into two
    equal halves, each half averaged, the halves correlated per unit, and the
    mean corrected to full length by 2r / (1 + r).

    The split is the contiguous one — first half against second half — because
    it has to be deterministic. A ceiling that moves between two calls on the
    same data rescales every result reported beneath it by a different amount
    each run. With an odd number of repeats the last is dropped, since
    Spearman-Brown's correction assumes two halves of equal length.

    A non-positive split-half correlation returns 0: two halves of the same
    measurement that do not agree carry no reliable signal, and a negative
    ceiling is not a ceiling.
    """
    r = np.asarray(repeats, dtype=float)
    if r.ndim != 3:
        raise ValueError(
            "repeats has shape %r; a noise ceiling is estimated from "
            "(n_repeats, n_windows, n_units)" % (r.shape,))
    n = r.shape[0]
    if n < 2:
        raise ValueError(
            "a noise ceiling needs at least two presentations of the same "
            "stimulus, and this has %d. It cannot be guessed from a single "
            "presentation: there is nothing to correlate the measurement "
            "against, so the only available answers are a made-up number and a "
            "refusal. A guessed ceiling silently rescales every result reported "
            "beneath it." % n)
    half = n // 2
    a = r[:half].mean(axis=0)
    b = r[half:2 * half].mean(axis=0)
    rho = float(_column_pearson(a, b).mean())
    if rho <= 0.0:
        return 0.0
    return float(2.0 * rho / (1.0 + rho))


#: Folds for every cross-validated fit below. Contiguous, never interleaved.
#:
#: Brain responses to continuous language are strongly autocorrelated in time —
#: neighbouring windows share a haemodynamic response and usually a sentence. An
#: interleaved fold puts window i in training and window i+1 in test, so the
#: model is scored on material it has effectively already seen, and every floor
#: measured that way sits far above the truth.
_N_FOLDS = 5
#: Ridge on z-scored features. Present so the fit is defined when a feature set
#: is wider than the number of windows, which is the normal case for the
#: size-matched control.
_RIDGE = 1.0


def _cv_encoding_score(features: np.ndarray, responses: np.ndarray) -> float:
    """Mean per-unit correlation of a cross-validated linear encoding model.

    The one scoring path shared by the floor and the control, so that when the
    two are compared the comparison is about the features and not about how each
    was fitted. Deterministic in its inputs: contiguous folds, no shuffling, no
    seed of its own.
    """
    X = np.asarray(features, dtype=float)
    Y = np.asarray(responses, dtype=float)
    if X.ndim != 2 or Y.ndim != 2:
        raise ValueError("features %r and responses %r must both be "
                         "(n_windows, ...)" % (X.shape, Y.shape))
    n = X.shape[0]
    if n != Y.shape[0]:
        raise ValueError(
            "%d feature rows against %d response rows. Row i of each must be "
            "the same stimulus window; see INTERFACE." % (n, Y.shape[0]))
    folds = int(min(_N_FOLDS, n))
    if folds < 2:
        raise ValueError("%d window(s) cannot be cross-validated" % n)

    pred = np.zeros_like(Y, dtype=float)
    bounds = np.linspace(0, n, folds + 1).astype(int)
    eye = np.eye(X.shape[1])
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        if hi <= lo:
            continue
        train = np.ones(n, dtype=bool)
        train[lo:hi] = False
        if not train.any():
            continue
        Xtr, Ytr = X[train], Y[train]
        mu = Xtr.mean(axis=0)
        # Scaled to unit variance so `_RIDGE` means the same thing to the raw
        # stimulus descriptors and to a 4096-wide candidate. An unscaled penalty
        # is a penalty on whichever feature set happened to be measured in
        # larger units, which would make the floor and the control incomparable.
        sd = Xtr.std(axis=0)
        sd[sd == 0] = 1.0
        Ztr = (Xtr - mu) / sd
        ym = Ytr.mean(axis=0)
        W = np.linalg.solve(Ztr.T @ Ztr + _RIDGE * eye, Ztr.T @ (Ytr - ym))
        pred[lo:hi] = ((X[lo:hi] - mu) / sd) @ W + ym
    return float(_column_pearson(pred, Y).mean())


def fit_stimulus_only_floor(stimulus: np.ndarray,
                            responses: np.ndarray) -> float:
    """How much of the response is predictable from the stimulus alone.

    The bar a language model has to clear to have contributed anything: word
    rate, length, frequency, position — properties of the text that need no
    model of meaning to compute.

    The signature is the enforcement. There is no parameter through which a
    candidate could arrive, because a floor fitted with the candidate in hand
    rises to meet whatever it is the floor for and can then only be beaten by
    luck. The docstring saying so would not have been enough; the absent
    argument is.
    """
    return _cv_encoding_score(stimulus, responses)


def fit_candidate_score(features: np.ndarray,
                        responses: np.ndarray) -> float:
    """A candidate representation's cross-validated encoding score.

    The candidate hands in FEATURES — one row per stimulus window — and the
    readout is fitted here, outside the sandbox, through the same path as the
    floor and the control. That is what makes the three comparable: they differ
    in what the features are and in nothing else. It is also what makes the
    subject split enforceable, since a candidate that predicted unit responses
    directly would have to have been shown the units it is scored on.
    """
    return _cv_encoding_score(features, responses)


def size_matched_control(stimulus: np.ndarray, responses: np.ndarray,
                         n_features: int, seed: int = 0) -> float:
    """The same width, drawn at random: what dimensionality alone buys.

    A representation the size of a modern transformer layer predicts a few
    hundred windows well more or less whatever it contains, so "beats the
    stimulus-only floor" is not yet news. This is the second bar: a random
    nonlinear expansion of the same stimulus to the same width, fitted and
    scored through the identical path. A candidate that ties it has demonstrated
    its dimensionality and nothing else.

    Random projection followed by tanh, rather than a bare linear projection: a
    linear map of an 8-dimensional stimulus is still 8-dimensional however wide
    it is written, so it reproduces the floor exactly and the control would test
    nothing. The nonlinearity is what makes the width real, which is also what
    makes it the right control for a candidate whose width is real.

    Seeded and reproducible. An unseeded control is a bar that moves between the
    run that proposed a candidate and the run that checked it.
    """
    X = np.asarray(stimulus, dtype=float)
    k = int(n_features)
    if k < 1:
        raise ValueError("a size-matched control needs at least one feature, "
                         "got %d" % k)
    rng = np.random.default_rng(int(seed))
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    proj = rng.normal(size=(Z.shape[1], k)) / np.sqrt(Z.shape[1])
    return _cv_encoding_score(np.tanh(Z @ proj + rng.normal(size=k)), responses)


def validate_subject_disjoint(train_subjects: Iterable[str],
                              test_subjects: Iterable[str]) -> None:
    """Refuse a split that puts the same person on both sides.

    Unit responses are strongly idiosyncratic. A model that has seen any of
    subject s2's data predicts the rest of s2 far better than it predicts anyone
    new, and the number it earns is about s2. `cancer` had exactly this
    corrected after the fact, and it went unnoticed because nothing asserted it.
    """
    train: List[str] = [str(s) for s in train_subjects]
    test: List[str] = [str(s) for s in test_subjects]
    if not train or not test:
        raise ValueError("a split needs subjects on both sides; got %d train "
                         "and %d test" % (len(train), len(test)))
    shared = sorted(set(train) & set(test))
    if shared:
        raise ValueError(
            "%s on both sides of the split. A model fitted on a subject and "
            "scored on that same subject is being measured on the person, not "
            "on language: the split is the SUBJECT, always."
            % ", ".join("subject %s" % s for s in shared))


# ---------------------------------------------------------------- the score

@dataclass(frozen=True)
class BrainScore:
    """A correlation with the two numbers that make it readable, or nothing.

    Both are required at CONSTRUCTION rather than checked when the score is
    reported. That closes the window in which a floor-less, ceiling-less score
    exists as an object and gets logged, cached or passed along: there is no
    moment at which a bare correlation is a value in this program.
    """

    correlation: float
    floor: Optional[float]
    ceiling: Optional[float]
    n_subjects: int

    def __post_init__(self) -> None:
        for name, v in (("floor", self.floor), ("ceiling", self.ceiling)):
            # NaN is refused alongside None, and for a second reason: a NaN
            # ceiling arrives from a division by zero somewhere upstream and
            # then propagates through every comparison as False, so a score
            # carrying one reads as "did not beat the floor" rather than as
            # broken.
            if v is None or not np.isfinite(float(v)):
                raise ValueError(
                    "%s is %r, so this is a correlation of %r with nothing to "
                    "read it against. A correlation without its floor and its "
                    "ceiling is not a result: r = 0.4 is nearly everything the "
                    "measurement permits against a ceiling of 0.42 and half of "
                    "it against 0.85, and without a floor there is no way to "
                    "know whether word rate alone already got there."
                    % (name, v, self.correlation))
        if not np.isfinite(float(self.correlation)):
            raise ValueError("correlation is %r, which is not a measurement"
                             % (self.correlation,))

    @property
    def normalized(self) -> float:
        """Where the correlation sits between the floor and what the
        measurement permits. Monotone in the raw correlation, by construction."""
        span = float(self.ceiling) - float(self.floor)
        if span <= 0:
            raise ValueError(
                "floor %.6g is at or above the noise ceiling %.6g, so there is "
                "no band to normalise into. That is an arithmetic warning, not "
                "a good result: it means the stimulus-only model reaches what "
                "the repeats say the data can support, and the ceiling or the "
                "floor is being computed on the wrong units."
                % (float(self.floor), float(self.ceiling)))
        return (float(self.correlation) - float(self.floor)) / span

    @property
    def is_improvement(self) -> bool:
        """Strictly above the floor. A tie has shown nothing — and the floor
        handed in here is the HIGHER of the stimulus-only fit and the
        size-matched control; see `_score_brainlang` in domains.py."""
        return float(self.correlation) > float(self.floor)
