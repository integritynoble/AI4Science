"""The human-brain language benchmark, and the nine ways it must refuse.

Encoding models of language cortex are unusually easy to fool, and every way of
fooling one has already been published as a result:

  * a corpus that is not on the machine, quietly replaced by simulated
    responses, so the number describes a random-number generator;
  * a "floor" fitted with the candidate in hand, which is not a floor but a
    second look at the answer;
  * a correlation reported bare, with no noise ceiling — 0.12 is either most of
    what the signal permits or almost none of it, and without the ceiling the
    reader cannot tell which;
  * a split that puts subject s2 on both sides, so the model is scored on the
    person it was fitted to;
  * a candidate that beats nothing but its own novelty — a representation of the
    same size, drawn at random, does as well.

So these tests are written against the refusals, not the happy path. Each
docstring says which claim the rule protects, because a rule whose reason is
lost gets deleted by the next person who finds it inconvenient.

They are RED on purpose right now: `runners/brainlang.py` and `HUMANBRAIN` do
not exist yet. The tests are the specification.
"""
from __future__ import annotations

import ast
import inspect
import math
from pathlib import Path

import numpy as np
import pytest


def _brainlang():
    """Imported inside each test rather than at module scope.

    A top-level import of an absent module collapses nine rules into one
    collection error, and the red run should name every rule that is missing —
    that list is the work order."""
    from ai4science.harness.agents.research_agents.runners import brainlang
    return brainlang


def _humanbrain():
    from ai4science.harness.agents.research_agents.runners import domains
    return domains.HUMANBRAIN


# ------------------------------------------------------------- the fixtures
#
# In memory, always. Nothing here writes a corpus to disk: a test that can
# manufacture the real data is a test that proves the benchmark will accept
# manufactured data.

@pytest.fixture
def stimulus() -> np.ndarray:
    """(n_items, n_stimulus_features) — what was read, described in the terms
    every model of it shares: length, frequency, position."""
    rng = np.random.default_rng(11)
    return rng.normal(size=(120, 8))


@pytest.fixture
def responses(stimulus) -> np.ndarray:
    """(n_items, n_voxels) — measured responses that genuinely carry some of the
    stimulus, so a floor fitted on them is a real floor rather than zero."""
    rng = np.random.default_rng(12)
    mix = rng.normal(size=(stimulus.shape[1], 30))
    return stimulus @ mix + rng.normal(size=(stimulus.shape[0], 30))


# ---------------------------------------------------------------- 1. the API

def test_the_module_declares_what_the_corpus_must_contain(stimulus):
    """A corpus interface stated in code, not in a README.

    Every other runner here reads data whose shape is implied by whichever
    generator happened to write it. That works while one person holds both ends
    and fails the moment a corpus is fetched by someone else: the arrays load,
    the axes are transposed, and the correlation is computed across voxels
    instead of items. So `INTERFACE` names the required fields AND their shapes,
    and this test holds it to naming both — a field list without shapes is the
    half of the contract that does not catch the transpose."""
    bl = _brainlang()
    from ai4science.harness.agents.research_agents.runners import corpus as _c

    assert isinstance(bl.BRAIN_LANGUAGE, _c.Corpus)
    assert bl.BRAIN_LANGUAGE.key == "brain-language"
    assert bl.BRAIN_LANGUAGE.required, "a corpus with no required files is always present"

    iface = bl.INTERFACE
    text = iface if isinstance(iface, str) else "\n".join(
        "%s: %s" % (k, v) for k, v in dict(iface).items())
    assert text.strip(), "an empty interface documents nothing"

    for f in bl.BRAIN_LANGUAGE.required:
        stem = Path(f).stem
        assert stem in text, (
            "%r is required on disk but the interface never says what is in it; "
            "the reader fetching this corpus has no way to check it" % f)
    assert any(w in text for w in ("shape", "n_items", "(n_", "axis")), (
        "the interface names fields but not shapes, which is the half that "
        "catches a transposed response matrix:\n%s" % text)


# ------------------------------------------------------- 2. absence refuses

def test_an_absent_corpus_says_what_is_missing_and_where_it_was_looked_for(tmp_path):
    """`CorpusMissing` is only useful if it is actionable.

    "brain-language not found" sends the reader to grep. The message has to
    carry the three things they need to fix it themselves: which corpus, which
    directory was searched, and which files were not in it. This mirrors
    `corpus.Corpus.require`, which already does exactly this for the other
    seven — brainlang must not invent a quieter second style."""
    bl = _brainlang()
    from ai4science.harness.agents.research_agents.runners import corpus as _c

    with pytest.raises(_c.CorpusMissing) as e:
        bl.load_corpus(root=tmp_path)
    msg = str(e.value)

    assert "brain-language" in msg or bl.BRAIN_LANGUAGE.title in msg, msg
    assert str(tmp_path) in msg, "the message never says where it looked:\n%s" % msg
    assert any(f in msg for f in bl.BRAIN_LANGUAGE.required), \
        "the message never names a missing file:\n%s" % msg


# ------------------------------------------------- 3. no synthetic fallback

def test_no_code_path_substitutes_simulated_responses(tmp_path):
    """The failure this whole benchmark is built to refuse.

    A missing corpus that falls back to simulated responses produces a number
    that looks like a result and is not, and nothing downstream — not the
    verdict, not the report — can tell the difference afterwards. The
    protection cannot be a convention; it has to be checkable.

    Two earlier drafts of this test banned the STRING "np.random" from the
    module's source, and that was wrong twice over. `size_matched_control` is a
    random projection BY DEFINITION — a control representation of the
    candidate's dimensionality, drawn without regard to the stimulus — so the
    ban forbade the module from implementing its own specification. And a
    source-text ban tests spelling rather than behaviour: it is defeated by
    `getattr(np, "rand" + "om")` and passes a module that fakes everything.

    So the check follows the mechanism the docstring actually names: the
    fallback is "one except-clause away". A generator only becomes a fallback
    when something CATCHES the refusal. Hence:

      * behaviourally, every entry point that can be pointed at a corpus root
        raises `CorpusMissing` on an empty one — none of them returns data;
      * structurally, no `except` in this module is positioned to swallow that
        refusal, checked by walking the AST rather than by grepping for words.

    `CorpusMissing` subclasses `FileNotFoundError` subclasses `OSError`, so all
    three are named: catching the base class catches the refusal just as
    completely as catching it by name, and a bare `except:` catches everything.
    """
    bl = _brainlang()
    from ai4science.harness.agents.research_agents.runners import corpus as _c

    # 1. The named entry point refuses, and returns nothing on the way.
    with pytest.raises(_c.CorpusMissing):
        got = bl.load_corpus(root=tmp_path)
        pytest.fail("load_corpus returned %r for an empty root instead of "
                    "refusing" % (got,))

    # 2. And so does everything else that can be aimed at a root. `load_corpus`
    #    being strict is worth nothing if some sibling reader is lenient — the
    #    caller reaches for whichever one is in front of them.
    checked = []
    for name in sorted(dir(bl)):
        if name.startswith("_"):
            continue
        fn = getattr(bl, name)
        if not callable(fn) or inspect.isclass(fn):
            continue
        if getattr(fn, "__module__", None) != bl.__name__:
            continue
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            continue
        if "root" not in params:
            continue
        checked.append(name)
        with pytest.raises(_c.CorpusMissing):
            got = fn(root=tmp_path)
            pytest.fail("%s(root=<empty dir>) returned %r instead of refusing; "
                        "whatever it returned did not come from a brain"
                        % (name, got))
    assert "load_corpus" in checked, (
        "no callable taking `root` was found, so nothing was actually "
        "exercised: %s" % sorted(dir(bl)))

    # 3. Nothing in the module is positioned to catch the refusal and carry on.
    src = Path(inspect.getsourcefile(bl)).read_text()
    swallows = {"CorpusMissing", "FileNotFoundError", "OSError", "IOError",
                "EnvironmentError", "Exception", "BaseException"}
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        caught = node.type
        assert caught is not None, (
            "bare `except:` at line %d of brainlang.py. It catches the missing"
            "-corpus refusal along with everything else, and whatever runs "
            "after it runs without data." % node.lineno)
        parts = caught.elts if isinstance(caught, ast.Tuple) else [caught]
        names = {p.attr if isinstance(p, ast.Attribute) else
                 p.id if isinstance(p, ast.Name) else ast.dump(p)
                 for p in parts}
        assert not (names & swallows), (
            "`except %s` at line %d of brainlang.py catches the refusal that a "
            "missing corpus raises (CorpusMissing is a FileNotFoundError is an "
            "OSError). This is the one except-clause that turns any generator "
            "in reach into a silent fallback."
            % (", ".join(sorted(names & swallows)), node.lineno))


# ------------------------------------------------ 4. the floor is blind

def test_the_floor_cannot_see_the_candidate(stimulus, responses):
    """A floor fitted with the candidate in hand is not a floor.

    The stimulus-only floor answers "how much of this response is predictable
    from properties of the text that no language model is needed for" — word
    rate, length, frequency, position. If the candidate's features can reach
    that fit, the floor rises to meet whatever it is being compared against and
    can never be beaten by an honest margin, only by a lucky one.

    Enforced twice, because a docstring is not an enforcement: the signature has
    no parameter the candidate could arrive through, and the value is
    bit-identical across two entirely different candidate feature sets."""
    bl = _brainlang()

    sig = inspect.signature(bl.fit_stimulus_only_floor)
    forbidden = {"candidate", "candidates", "prediction", "predictions", "pred",
                 "preds", "candidate_features", "model_features", "features"}
    named = set(sig.parameters)
    assert not (named & forbidden), (
        "fit_stimulus_only_floor%s takes %s — the floor must not be able to "
        "see what it is the floor for" % (sig, sorted(named & forbidden)))

    rng = np.random.default_rng(3)
    candidate_a = rng.normal(size=(stimulus.shape[0], 64))
    candidate_b = rng.normal(size=(stimulus.shape[0], 512)) * 40.0
    assert not np.allclose(candidate_a.mean(), candidate_b.mean())

    first = bl.fit_stimulus_only_floor(stimulus, responses)
    second = bl.fit_stimulus_only_floor(stimulus, responses)
    assert np.float64(first).tobytes() == np.float64(second).tobytes(), (
        "the floor moved between two calls on identical data (%r vs %r); a "
        "floor that is not deterministic cannot be a bar" % (first, second))
    assert math.isfinite(float(first))


# -------------------------------------- 5. not beating the floor is not news

def test_a_candidate_that_does_not_beat_the_floor_is_no_improvement(stimulus, responses):
    """The bar is the floor, and the floor is whichever of two is higher.

    A representation the size of a modern layer explains variance by being
    large — 4096 arbitrary dimensions fit a hundred items well whatever they
    contain. So the candidate is measured against both the stimulus-only floor
    AND a size-matched control of the same dimensionality, and the score's
    `is_improvement` is False unless it clears the higher of them. A model that
    ties the control has demonstrated its dimensionality."""
    bl = _brainlang()

    floor = float(bl.fit_stimulus_only_floor(stimulus, responses))
    control = float(bl.size_matched_control(stimulus, responses,
                                            n_features=64, seed=0))
    again = float(bl.size_matched_control(stimulus, responses,
                                          n_features=64, seed=0))
    assert control == again, "the control must be reproducible from its seed"

    bar = max(floor, control)
    ceiling = max(bar + 0.2, 0.8)

    below = bl.BrainScore(correlation=bar - 0.05, floor=bar, ceiling=ceiling,
                          n_subjects=8)
    assert below.is_improvement is False, (
        "%r beats neither the stimulus-only floor nor a size-matched control "
        "and was scored as an improvement" % (below,))

    tied = bl.BrainScore(correlation=bar, floor=bar, ceiling=ceiling, n_subjects=8)
    assert tied.is_improvement is False, "a tie with the floor is not a gain"

    above = bl.BrainScore(correlation=bar + 0.1, floor=bar, ceiling=ceiling,
                          n_subjects=8)
    assert above.is_improvement is True, above

    # Normalised against the ceiling, and monotone in the raw correlation.
    # The exact normalisation is the module's business; that a better model
    # cannot normalise to a worse number is not.
    assert above.normalized > below.normalized


# ------------------------------------- 6. a bare correlation is not a result

def test_a_report_without_a_floor_and_a_ceiling_is_rejected():
    """r = 0.4 is unreadable on its own.

    Against a noise ceiling of 0.42 it is nearly everything the measurement
    permits; against 0.85 it is half. And with no floor there is no way to know
    whether word rate alone already got there. Both are required at
    construction rather than checked at report time, so there is no window in
    which a scoreless score exists and gets logged.

    NaN is refused for the same reason as None, and separately: a NaN ceiling
    arrives from a division by zero somewhere upstream and then propagates
    silently through every comparison as False."""
    bl = _brainlang()

    with pytest.raises(ValueError):
        bl.BrainScore(correlation=0.4, floor=None, ceiling=0.8, n_subjects=8)
    with pytest.raises(ValueError):
        bl.BrainScore(correlation=0.4, floor=0.1, ceiling=None, n_subjects=8)
    with pytest.raises(ValueError):
        bl.BrainScore(correlation=0.4, floor=0.1, ceiling=float("nan"),
                      n_subjects=8)
    with pytest.raises(ValueError):
        bl.BrainScore(correlation=0.4, floor=float("nan"), ceiling=0.8,
                      n_subjects=8)

    ok = bl.BrainScore(correlation=0.4, floor=0.1, ceiling=0.8, n_subjects=8)
    with pytest.raises(Exception):
        ok.correlation = 0.9      # frozen: a score is a record, not a variable


# --------------------------------------------- 7. subjects do not span a split

def test_a_within_subject_split_is_rejected():
    """Scoring a model on the person it was fitted to is not generalisation.

    Voxel responses are strongly idiosyncratic; a model that has seen any of
    subject s2's data predicts the rest of s2 far better than it predicts anyone
    new, and the resulting number is about s2. `cancer` had to have exactly this
    corrected after the fact, and it went unnoticed because nothing asserted it
    — so it is asserted here before there is anything to assert it against."""
    bl = _brainlang()

    with pytest.raises(ValueError) as e:
        bl.validate_subject_disjoint(["s1", "s2"], ["s2", "s3"])
    assert "s2" in str(e.value), (
        "the error must name the subject that spans the split:\n%s" % e.value)

    assert bl.validate_subject_disjoint(["s1", "s2"], ["s3", "s4"]) is None


# ------------------------------------------------ 8. the ceiling is measured

def test_the_noise_ceiling_comes_from_repeats_and_refuses_to_be_guessed():
    """Estimated from repeated presentations, or not reported.

    The ceiling is the correlation the same brain achieves with itself across
    repeats — it is a measurement, not a constant, and it differs by subject and
    by region. With a single presentation there is nothing to correlate against
    and the only available answers are a made-up one or a refusal. It refuses:
    a guessed ceiling silently rescales every result reported beneath it."""
    bl = _brainlang()

    rng = np.random.default_rng(7)
    signal = rng.normal(size=(100, 12))

    with pytest.raises(ValueError):
        bl.noise_ceiling(signal[None, ...])          # one repeat

    clean = np.stack([signal + 0.01 * rng.normal(size=signal.shape)
                      for _ in range(4)])
    noisy = np.stack([signal + 2.0 * rng.normal(size=signal.shape)
                      for _ in range(4)])

    hi, lo = float(bl.noise_ceiling(clean)), float(bl.noise_ceiling(noisy))
    assert math.isfinite(hi) and math.isfinite(lo)
    assert hi <= 1.0 + 1e-9, "a ceiling above 1 is an arithmetic error: %r" % hi
    assert hi > lo, (
        "reliable repeats (%.4f) must not yield a lower ceiling than unreliable "
        "ones (%.4f) — the estimator is not reading the repeats" % (hi, lo))


# ------------------------------------------- 9. the key is withheld, as always

def test_humanbrain_withholds_an_answer_key_like_the_other_six():
    """The benchmark is outside the agent's reach as a file permission.

    `common.run_domain_task` withholds exactly the paths in `answer_key` and
    stages everything else. An empty tuple therefore means the solver receives
    the held-out responses it is being scored against — which for an encoding
    model is the entire task. The convention is workspace-RELATIVE posix paths,
    because that is what the staging loop compares against; an absolute path
    matches nothing and is withheld from nobody, silently."""
    hb = _humanbrain()
    from ai4science.harness.agents.research_agents.runners.common import DomainBenchmark

    assert isinstance(hb, DomainBenchmark)
    assert isinstance(hb.answer_key, tuple)
    assert hb.answer_key, (
        "HUMANBRAIN withholds nothing; the solver would be handed the responses "
        "it is scored against")
    for p in hb.answer_key:
        assert isinstance(p, str) and p
        assert not p.startswith("/") and ".." not in p and "\\" not in p, (
            "%r is not a workspace-relative posix path, so the staging loop in "
            "run_domain_task will never match it" % p)
    assert hb.corpus == "brain-language", (
        "a result from generated data is evidence about a method, never about a "
        "brain")
