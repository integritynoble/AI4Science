"""The solver half of the human-brain benchmark, and what it may never reach.

`payload/brainlang/` has a generator and no `run_solver.py`. `HUMANBRAIN`
names two deliverables — `results/features_train.npy` and
`results/features_heldout.npy` — and nothing on this machine produces them, so
the benchmark stands defined and un-runnable. These tests are the specification
for the missing half, written before it exists, and they are RED on purpose:
every one of them fails today because the file they execute is not there.

The claims they hold it to are not stylistic. An encoding-model solver sits in
a sandbox next to the answer key's absence, and the three ways it can produce a
number that looks like a result are all cheap:

  * read the held-out responses — `data/test_responses.npz`, `data/test_repeats
    .npz` — and hand back a representation that is really a copy of the answer.
    The staging loop in `run_domain_task` withholds exactly those two paths, and
    the honest proof of that is behavioural: run the solver where they are
    unreadable and check nothing changes;
  * score itself. The candidate hands in FEATURES and the linear readout is
    fitted outside the sandbox by `_score_brainlang`, through the same path as
    the floor and the size-matched control. That is what makes the three
    comparable. A solver that imported `brainlang` and reported its own
    correlation would be a candidate marking its own paper;
  * manufacture features. `brainlang.py` is allowed its `np.random` —
    `size_matched_control` IS a random projection, by definition — and the
    solver is not: it has no legitimate use for a random number, and a
    representation drawn from one predicts held-out responses at exactly the
    level of the control it is supposed to beat.

Every fixture here is built from tmp_path and stimulus alone. A stimulus can be
synthesised because the stimulus is not the answer key — `generate.py` says so
where it counts frequencies over the held-out windows too — but no brain
response is invented anywhere in this file. Where the tests need the answer key
to EXIST (to have something for the staging loop to withhold, or something for
a curious solver to trip over), what gets written is an unreadable placeholder,
never a plausible response matrix. A test that can manufacture the real data is
a test that proves the benchmark will accept manufactured data.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


# ------------------------------------------------------------ locating things

def _humanbrain():
    """HUMANBRAIN by name, never through `benchmark_for`.

    It is deliberately absent from `BENCHMARKS` — `corpus.ALL` has no
    "brain-language" key, and registering it would turn conftest's
    `needs_corpus` lookup into a KeyError for every parametrised test. So the
    lookup here is the attribute, and a day when this benchmark joins the
    registry must not be the day these tests start passing for a new reason."""
    from ai4science.harness.agents.research_agents.runners import domains
    return domains.HUMANBRAIN


def _payload_dir() -> Path:
    """`runners/payload/<package>`, derived from the module that declares it."""
    from ai4science.harness.agents.research_agents.runners import domains
    hb = _humanbrain()
    return Path(domains.__file__).resolve().parent / "payload" / hb.package


def _solver_path() -> Path:
    return _payload_dir() / "run_solver.py"


def _solver_source() -> str:
    """The solver's source, or the one failure every test here shares.

    Asserted rather than skipped. A skip on an absent solver would report this
    whole file as "nothing to check" on exactly the machine where nothing has
    been written yet, and the red list is the work order."""
    p = _solver_path()
    assert p.is_file(), (
        "%s does not exist. HUMANBRAIN names results/features_train.npy and "
        "results/features_heldout.npy as its deliverables and payload/%s "
        "contains only generate.py, so no code on this machine produces them: "
        "the benchmark is defined and cannot be run end to end."
        % (p, _humanbrain().package))
    return p.read_text()


def _solver_ast() -> ast.Module:
    return ast.parse(_solver_source())


# ---------------------------------------------------------------- the fixture
#
# What the solver is entitled to see, and not one file more. Built from
# tmp_path, from a synthesised stimulus and the generator's own descriptor code
# — never from invented responses.

#: Enough windows for the split `generate.py` would cut: it refuses fewer than
#: 20 repeated windows, and the repeated ones are the FINAL k of the sequence.
N_WINDOWS = 160
N_HELDOUT = 40
#: `MIN_TEST_SUBJECTS` is 3 in the generator, and the split is by SUBJECT.
TRAIN_SUBJECTS = ("s01", "s02", "s03", "s04", "s05")
TEST_SUBJECTS = ("s06", "s07", "s08")

#: What stands in for the answer key where a test needs it to exist.
#:
#: Not an npz, and not a number. The two files it is written to are the
#: held-out subjects' responses and their repeated presentations; writing
#: anything loadable there would put a plausible brain response on disk in a
#: test file, which is the failure this benchmark exists to refuse. A solver
#: that opens either one gets bytes that are not an archive — and, in the test
#: that matters, does not get to open them at all.
PLACEHOLDER_KEY = (
    b"This is not a response matrix. It stands where the answer key would be "
    b"so the staging loop has something to withhold. No brain produced these "
    b"bytes and no test in this file will invent one that did.\n")

#: A fixed vocabulary, walked deterministically. Nothing here is drawn at
#: random: the fixture is compared byte-for-byte across workspaces and runs.
_VOCAB = ("the", "cortex", "listened", "to", "a", "long", "story", "about",
          "language", "and", "remembered", "almost", "none", "of", "it")


def _stimulus() -> list:
    """The text, in window order, laid out the way INTERFACE requires.

    Synthesised, and that is allowed: the stimulus is not the answer key. The
    responses are. `generate.py` makes the same distinction when it counts token
    frequencies over the held-out windows and calls it not-leakage."""
    out = []
    for i in range(N_WINDOWS):
        n_tok = 1 + (i % 4)
        toks = [_VOCAB[(i * 7 + j * 3) % len(_VOCAB)] for j in range(n_tok)]
        onset = 2.0 * i
        out.append({"token": toks, "onset_s": onset, "offset_s": onset + 1.5})
    return out


def _generate_module():
    """The generator's `stimulus_descriptors`, loaded from the payload by path.

    Imported rather than reimplemented. The descriptors staged for the solver
    are whatever that function computes, and a second copy of the arithmetic
    here would let the fixture drift from the thing it stands in for — quietly,
    since both sides would still produce an 8-wide matrix.

    By path because payload/ is a directory of scripts rather than an importable
    package. Only the module body runs: `main()`, which is the half that calls
    `load_corpus` and refuses, is behind the __main__ guard."""
    p = _payload_dir() / "generate.py"
    assert p.is_file(), "%s is missing; the payload has no generator" % p
    spec = importlib.util.spec_from_file_location("_brainlang_generate", p)
    mod = importlib.util.module_from_spec(spec)
    # No .pyc left behind: `_seed_key` hashes the payload directory's files and
    # `files()` enumerates it, so a test that drops bytecode into the package
    # under test is a test editing the thing it measures.
    was = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = was
    return mod


def _build_workspace(root: Path, *, with_answer_key: bool = False) -> Path:
    """A workspace shaped exactly like the one `run_domain_task` executes in.

    `code/` carries what `seed_workspace` copies — `bench.files()`, verbatim —
    and `data/` carries what the generator writes MINUS the answer key, which
    is what the staging loop leaves behind.

    `with_answer_key` writes the two withheld paths as unreadable placeholders.
    It is for the two tests that need the key to exist: the one that replicates
    the staging loop (a loop that withholds nothing when there is nothing to
    withhold proves nothing) and the one that puts the key in the solver's
    reach and checks it stays untouched.

    `data/train_responses.npz` is the honest awkwardness here. The file belongs
    in the sandbox — the training subjects' responses are not the answer key —
    but no test may invent one, so it is written with the right keys, the right
    row count, and ZERO units: real structure, no fabricated numbers. That is
    not a hole in the fixture, it is the design showing through. The candidate
    hands in features and `_score_brainlang` fits the readout outside the
    sandbox, so a solver that cannot emit a representation of the text without
    real response values in front of it is already doing something this
    benchmark does not ask for.
    """
    hb = _humanbrain()
    ws = Path(root)
    (ws / "code").mkdir(parents=True, exist_ok=True)
    for p in hb.files():
        (ws / "code" / p.name).write_bytes(p.read_bytes())

    gen = _generate_module()
    stimulus = _stimulus()
    train_idx = list(range(0, N_WINDOWS - N_HELDOUT))
    heldout_idx = list(range(N_WINDOWS - N_HELDOUT, N_WINDOWS))

    d = ws / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "stimulus.json").write_text(json.dumps(stimulus))
    (d / "split.json").write_text(json.dumps({
        "train_subjects": list(TRAIN_SUBJECTS),
        "test_subjects": list(TEST_SUBJECTS),
        "train_windows": train_idx,
        "heldout_windows": heldout_idx}))
    np.save(d / "train_features.npy", gen.stimulus_descriptors(stimulus, train_idx))
    np.save(d / "heldout_features.npy", gen.stimulus_descriptors(stimulus, heldout_idx))
    np.savez_compressed(
        d / "train_responses.npz",
        **{s: np.zeros((len(train_idx), 0), dtype=np.float32)
           for s in TRAIN_SUBJECTS})

    if with_answer_key:
        for rel in hb.answer_key:
            f = ws / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(PLACEHOLDER_KEY)
    return ws


@pytest.fixture
def workspace(tmp_path) -> Path:
    """The sandbox as the solver receives it: no answer key, anywhere."""
    return _build_workspace(tmp_path / "run")


def _run_solver(ws: Path) -> subprocess.CompletedProcess:
    """`python3 code/run_solver.py --workspace .` with cwd at the workspace.

    The same invocation `run_domain_task` hands to `sandbox_execute`, with
    sys.executable in place of `python3` so the subprocess has the numpy this
    interpreter has. `child_env` puts the repository on PYTHONPATH exactly as
    the harness does for a spawned child — which is deliberate here rather than
    incidental: it means `import brainlang` WOULD work, so the test asserting
    the solver does not do it is asserting a choice and not an ImportError."""
    from ai4science.harness.agents.research_agents.runners import common
    return subprocess.run(
        [sys.executable, "code/run_solver.py", "--workspace", "."],
        cwd=str(ws), capture_output=True, text=True, env=common.child_env())


def _must_run(ws: Path) -> subprocess.CompletedProcess:
    out = _run_solver(ws)
    assert out.returncode == 0, (
        "run_solver.py exited %d in %s. `run_domain_task` reports an erroring "
        "solver as status=failed and never reaches the judge, so this is the "
        "whole run.\nstderr:\n%s\nstdout:\n%s"
        % (out.returncode, ws, out.stderr[-2000:], out.stdout[-800:]))
    return out


def _deliverable_paths(ws: Path):
    hb = _humanbrain()
    train = next(x for x in hb.deliverables if "train" in Path(x).name)
    heldout = next(x for x in hb.deliverables if "heldout" in Path(x).name)
    return ws / train, ws / heldout


def _split(ws: Path) -> dict:
    return json.loads((ws / "data" / "split.json").read_text())


# ------------------------------------------------- 1. the package is complete

def test_the_payload_carries_a_solver_and_staging_picks_it_up():
    """A benchmark whose package has no solver cannot be run end to end.

    `seed_workspace` copies `bench.files()` into `code/`, and `files()` is every
    .py in `payload/<package>` — so the solver reaches the sandbox by being a
    file in that directory and by nothing else. Both halves are asserted: that
    `run_solver.py` is on disk beside `generate.py`, and that `files()` actually
    returns it, because a solver the staging loop does not enumerate is a solver
    that never arrives.

    The `.py` suffix is part of the contract for the same reason. `files()`
    filters on it, so a solver written as `run_solver` or `run_solver.py.txt`
    would sit in the payload directory and be staged by nothing."""
    hb = _humanbrain()
    solver = _solver_path()
    assert solver.is_file(), (
        "%s does not exist; payload/%s has a generator and no solver, so "
        "HUMANBRAIN's deliverables %s are produced by nothing"
        % (solver, hb.package, list(hb.deliverables)))

    names = [p.name for p in hb.files()]
    assert "generate.py" in names, (
        "files() does not enumerate the generator: %s" % names)
    assert "run_solver.py" in names, (
        "files() returns %s — run_solver.py is not among them, so "
        "seed_workspace copies it into no workspace and "
        "`python3 code/run_solver.py` has nothing to execute" % names)
    assert solver.resolve() in {p.resolve() for p in hb.files()}, (
        "files() returned a run_solver.py that is not %s" % solver)


# --------------------------------------------- 2. it produces both deliverables

def test_the_solver_writes_both_feature_matrices_with_the_shapes_scoring_needs(workspace):
    """Both deliverables, the row counts split.json implies, one shared width.

    `run_domain_task` checks only that the files exist; `_score_brainlang` is
    where the shapes are held to account, and it raises on two of them — a
    matrix that is not 2-D, and a train matrix whose width differs from the
    held-out one ("a representation fitted on one width and scored on another is
    two models wearing one name"). The row counts it does not raise on: they
    reach `fit_candidate_score`, where `_cv_encoding_score` refuses a feature/
    response row mismatch. All three are asserted here, in the sandbox, so the
    failure lands on the solver rather than eight files away in the scorer.

    The train matrix is required even though no held-out subject's training
    responses are the candidate's to see. It is the commitment: features over
    the whole session, not only the scored windows, so the candidate cannot
    special-case the held-out material — which is the final k of the sequence
    and therefore guessable."""
    _solver_source()          # names the missing file before the subprocess does
    _must_run(workspace)

    split = _split(workspace)
    train_out, heldout_out = _deliverable_paths(workspace)
    for f in (train_out, heldout_out):
        assert f.is_file(), (
            "%s is not there. run_domain_task reports "
            "'deliverables missing' and stops before the judge."
            % f.relative_to(workspace).as_posix())

    A = np.load(train_out, allow_pickle=False)
    B = np.load(heldout_out, allow_pickle=False)
    assert A.ndim == 2 and B.ndim == 2, (
        "candidate features must be (n_windows, n_features); got train %r and "
        "held-out %r, which _score_brainlang refuses" % (A.shape, B.shape))
    assert A.shape[0] == len(split["train_windows"]), (
        "%d training rows against %d train_windows in split.json — row i of the "
        "feature matrix IS stimulus window i, so a different count is a "
        "different alignment" % (A.shape[0], len(split["train_windows"])))
    assert B.shape[0] == len(split["heldout_windows"]), (
        "%d held-out rows against %d heldout_windows in split.json; these rows "
        "are correlated against the withheld responses one for one"
        % (B.shape[0], len(split["heldout_windows"])))
    assert A.shape[1] == B.shape[1], (
        "%d-wide for the training windows and %d-wide for the held-out ones: "
        "_score_brainlang raises on exactly this, because the size-matched "
        "control is drawn at the candidate's width and there would be two "
        "widths to match" % (A.shape[1], B.shape[1]))
    assert B.shape[1] >= 1, "a zero-wide representation predicts nothing"
    assert np.isfinite(A).all() and np.isfinite(B).all(), (
        "non-finite features reach _column_pearson as a NaN correlation, which "
        "BrainScore refuses only for the floor and the ceiling — a NaN "
        "candidate correlation would propagate through every comparison as "
        "False and read as 'did not beat the floor' rather than as broken")


# --------------------------------------------- 3. the answer key is unreachable

def test_the_sandbox_has_no_answer_key_and_the_solver_does_not_need_one(workspace):
    """Claim 3a: it succeeds on exactly what staging leaves behind.

    The fixture is built to the staging loop's rule — everything the generator
    writes except `data/test_responses.npz` and `data/test_repeats.npz` — so
    "the solver did not read the key" is not a promise about its source here,
    it is a fact about the run: the files are not in the tree. A solver that
    needed them could not have exited 0.

    Asserted over the whole tree rather than over `data/`, because a key that
    arrived anywhere — copied, cached, unpacked one directory over — is a key
    in the sandbox."""
    hb = _humanbrain()
    _solver_source()

    stems = {Path(k).stem for k in hb.answer_key}
    present = sorted(p.relative_to(workspace).as_posix()
                     for p in workspace.rglob("*") if p.is_file())
    leaked = [rel for rel in present
              if rel in hb.answer_key or Path(rel).stem in stems]
    assert not leaked, (
        "the fixture handed the sandbox %s; the staging loop withholds exactly "
        "%s and a test that stages them is testing a different benchmark"
        % (leaked, list(hb.answer_key)))

    _must_run(workspace)
    train_out, heldout_out = _deliverable_paths(workspace)
    assert train_out.is_file() and heldout_out.is_file(), (
        "the solver produced no features from stimulus alone, which is all the "
        "sandbox will ever contain: %s" % present)


def test_an_unreadable_answer_key_changes_nothing_the_solver_produces(tmp_path):
    """Claim 3b: put the key within reach, make it unopenable, compare bytes.

    Absence proves the solver *can* work without the key. It does not prove it
    would decline one that was there — a benchmark run gone wrong, a cache, a
    future generator that stages one file too many, and the solver's behaviour
    is whatever it always was. So the second workspace is identical to the first
    in every byte except that `data/test_responses.npz` and
    `data/test_repeats.npz` exist with mode 000.

    Reading either raises PermissionError, which is loud: the run fails, or the
    deliverables differ. Byte-identical outputs across the two runs is the
    strongest statement available from outside the process — the key was in the
    same relative path the generator writes it to, and it made no difference to
    anything the solver handed in.

    The placeholder bytes are not a response matrix and not an npz. Skipped
    politely as root, where mode 000 does not bite and the test would prove
    nothing while appearing to."""
    hb = _humanbrain()
    _solver_source()

    if getattr(os, "geteuid", None) is not None and os.geteuid() == 0:
        pytest.skip("running as root: mode 000 is not enforced, so an "
                    "unreadable file would be readable and this proves nothing")

    clean = _build_workspace(tmp_path / "clean")
    baited = _build_workspace(tmp_path / "baited", with_answer_key=True)

    keys = [baited / rel for rel in hb.answer_key]
    for f in keys:
        assert f.is_file(), "%s was not written" % f
        os.chmod(f, 0)
    try:
        for f in keys:
            try:
                with open(f, "rb"):
                    pytest.skip("%s is readable at mode 000 on this filesystem; "
                                "the bait is not baited" % f)
            except PermissionError:
                pass

        _must_run(clean)
        out = _run_solver(baited)
        assert out.returncode == 0, (
            "the solver exited %d when the answer key existed unreadable beside "
            "the data it is allowed to read — it opened a file that is not its "
            "to open.\nstderr:\n%s" % (out.returncode, out.stderr[-2000:]))
        assert "PermissionError" not in out.stderr, (
            "PermissionError in the solver's stderr: something reached for "
            "%s.\n%s" % (list(hb.answer_key), out.stderr[-2000:]))

        for a, b in zip(_deliverable_paths(clean), _deliverable_paths(baited)):
            assert b.is_file(), "%s was not produced in the baited workspace" % b
            assert a.read_bytes() == b.read_bytes(), (
                "%s differs between a workspace without the answer key and one "
                "where it sits unreadable next to the inputs. The only thing "
                "that changed is the presence of the held-out responses, so "
                "the representation is a function of them."
                % Path(a).name)
    finally:
        # Left readable so tmp_path teardown is not the thing that fails.
        for f in keys:
            os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)


# ------------------------------------------------ 4. it does not name the key

def test_the_solver_never_names_the_withheld_files():
    """The key's names appear nowhere in the solver — not even hopefully.

    Weaker than the behavioural tests above and it earns its place beside them:
    those run one solver against one fixture, and this reads every path through
    the source, including the branch that only fires when a file happens to be
    there. A `try: np.load("data/test_responses.npz") except OSError: pass` is
    invisible to a run in a sandbox that never had the file and is exactly what
    a solver would grow the first time someone ran it against a seed workspace.

    Two passes, because they catch different things. The raw text catches the
    name wherever it is written, comments and docstrings included — a solver
    that "documents" the path it would like is documenting an intention. The
    AST pass catches `"test_" "responses"`, which the parser folds into one
    constant and the raw text does not contain."""
    src = _solver_source()
    forbidden = ("test_responses", "test_repeats")

    for name in forbidden:
        assert name not in src, (
            "run_solver.py mentions %r. Those two files are HUMANBRAIN's "
            "answer_key: the held-out subjects' responses and the repeats the "
            "noise ceiling is measured from. A solver has no reason to know "
            "their names." % name)

    for node in ast.walk(_solver_ast()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in forbidden:
                assert name not in node.value, (
                    "the string constant at line %d of run_solver.py contains "
                    "%r — assembled from adjacent literals, which the raw "
                    "source does not show" % (node.lineno, name))


# --------------------------------------------- 5. it does not score itself

def test_the_solver_emits_features_and_scores_nothing(workspace):
    """The candidate hands in a representation; the judge decides what it is worth.

    This is the split that makes the whole benchmark enforceable.
    `_score_brainlang` fits the linear readout outside the sandbox, through the
    identical path as the stimulus-only floor and the size-matched control —
    that is what makes the three numbers comparable, and it is what makes the
    subject split enforceable, since a candidate that predicted unit responses
    directly would have to have been shown the units it is scored on.

    So the solver writes two feature matrices and nothing else. Three checks:

      * behaviourally, the only files that appear in the workspace are the two
        deliverables. A `results/score.json` would be a number the sandbox
        computed about itself, and the first reader to find one beside the
        judge's metrics has two numbers and no way to tell which is the result;
      * it does not import `brainlang`. `child_env` puts the repository on the
        child's PYTHONPATH, so the import would succeed — declining it is a
        choice being asserted, not an ImportError being observed;
      * it names none of the scoring API. `fit_stimulus_only_floor` is the one
        that matters most: a floor fitted with the candidate in hand rises to
        meet whatever it is the floor for, and the module keeps it honest by
        having no parameter a candidate can arrive through. A solver calling it
        with its own features is that parameter."""
    hb = _humanbrain()
    src = _solver_source()

    before = {p.relative_to(workspace).as_posix()
              for p in workspace.rglob("*") if p.is_file()}
    _must_run(workspace)
    after = {p.relative_to(workspace).as_posix()
             for p in workspace.rglob("*") if p.is_file()}

    # __pycache__ is the interpreter's bookkeeping for an imported helper, not
    # the solver's output; everything else that appeared is the solver's doing.
    written = {rel for rel in after - before if "__pycache__" not in rel}
    assert written == set(hb.deliverables), (
        "the solver wrote %s; HUMANBRAIN declares %s and the extras are the "
        "sandbox reporting on itself. Scoring happens outside, against the key "
        "the sandbox never received."
        % (sorted(written), sorted(hb.deliverables)))
    assert not (before - after), (
        "the solver removed %s from its own workspace" % sorted(before - after))

    tree = _solver_ast()
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""] + [a.name for a in node.names]
        assert not any("brainlang" in (m or "") for m in mods), (
            "run_solver.py imports brainlang at line %d. That module holds the "
            "floor, the control, the ceiling and BrainScore — every one of them "
            "belongs to the process that scores this candidate, not to the "
            "candidate." % node.lineno)

    scoring_api = {"fit_stimulus_only_floor", "noise_ceiling",
                   "size_matched_control", "fit_candidate_score", "BrainScore"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            named = {node.name}
        elif isinstance(node, ast.Attribute):
            named = {node.attr}
        elif isinstance(node, ast.Name):
            named = {node.id}
        else:
            continue
        hit = named & scoring_api
        assert not hit, (
            "run_solver.py refers to %s at line %d. Whether it calls the real "
            "one or defines its own of that name, the solver is computing the "
            "bar it is being measured against."
            % (", ".join(sorted(hit)), node.lineno))

    for name in sorted(scoring_api):
        assert name not in src, (
            "%r appears in run_solver.py's source. The judge scores; the "
            "candidate hands in features." % name)


# ------------------------------------------------ 6. no manufactured features

def test_no_code_path_manufactures_a_random_representation():
    """The fallback that would look exactly like a result.

    `brainlang.py` gets to use `np.random` — `size_matched_control` is a random
    projection BY DEFINITION, a representation of the candidate's own width
    drawn without regard to meaning. The solver is the other side of that
    control and has no legitimate use for a random number at all: its whole
    output is a function of the text it was given. A solver that drew one would
    hand in the control and be scored against it, and the two numbers would
    agree to within noise while looking like a measurement of a language model.

    Modelled on `test_no_code_path_substitutes_simulated_responses` in
    test_brainlang_benchmark.py, and it borrows that test's second half for the
    same reason: a generator only becomes a fallback when something CATCHES the
    refusal. The solver's inputs are files, so a missing input raises
    FileNotFoundError — an OSError — and an `except` positioned to swallow that
    is one line away from `features = np.random.normal(...)` and an exit code
    of 0. The clause is what turns absent data into a plausible matrix, so the
    clause is what is checked.

    A source walk cannot see `getattr(np, "rand" + "om")`, and this does not
    pretend otherwise: the behavioural half of the claim is
    test_the_solver_is_deterministic, which any live random number fails."""
    src = _solver_source()
    tree = ast.parse(src)

    #: `random` catches the module and `rng.random()`; `default_rng` and
    #: `RandomState` catch the two constructors that are usually reached for
    #: before either name is spelled again.
    rand_names = {"random", "default_rng", "RandomState"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] != "random" and \
                    not a.name.startswith("numpy.random"), (
                        "run_solver.py imports %s at line %d; the solver's "
                        "output must be a function of the stimulus alone"
                        % (a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imported = {a.name for a in node.names}
            assert mod.split(".")[0] != "random", (
                "run_solver.py imports from the random module at line %d"
                % node.lineno)
            assert not (mod.endswith("numpy.random") or mod == "numpy.random"), (
                "run_solver.py imports from numpy.random at line %d" % node.lineno)
            assert not (mod == "numpy" and (imported & rand_names)), (
                "run_solver.py imports %s from numpy at line %d"
                % (sorted(imported & rand_names), node.lineno))
        elif isinstance(node, ast.Attribute) and node.attr in rand_names:
            pytest.fail(
                "run_solver.py reaches `.%s` at line %d. Unlike brainlang.py — "
                "where the size-matched control IS a random projection — a "
                "solver has no legitimate use for randomness: a representation "
                "drawn from a generator predicts held-out responses at exactly "
                "the level of the control it is meant to beat, and the run "
                "still exits 0." % (node.attr, node.lineno))
        elif isinstance(node, ast.Name) and node.id in rand_names:
            pytest.fail("run_solver.py refers to `%s` at line %d"
                        % (node.id, node.lineno))

    swallows = {"OSError", "IOError", "EnvironmentError", "FileNotFoundError",
                "Exception", "BaseException"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        caught = node.type
        assert caught is not None, (
            "bare `except:` at line %d of run_solver.py. It catches the "
            "FileNotFoundError a missing input raises along with everything "
            "else, and whatever runs after it runs without data." % node.lineno)
        parts = caught.elts if isinstance(caught, ast.Tuple) else [caught]
        names = {p.attr if isinstance(p, ast.Attribute) else
                 p.id if isinstance(p, ast.Name) else ast.dump(p)
                 for p in parts}
        assert not (names & swallows), (
            "`except %s` at line %d of run_solver.py catches a missing input. "
            "The inputs are files; the solver should fail loudly when one is "
            "absent, because the alternative is a feature matrix that came "
            "from somewhere other than the stimulus and a workspace that looks "
            "complete." % (", ".join(sorted(names & swallows)), node.lineno))


# ------------------------------------------------------------ 7. determinism

def test_the_solver_is_deterministic_across_two_runs(workspace):
    """A representation that moves between runs cannot be checked by anyone.

    The behavioural half of the claim above: a live random number survives every
    source walk ever written and fails this in one line. And the requirement
    stands on its own, for the reason `noise_ceiling` gives about its contiguous
    split and `size_matched_control` gives about its seed — a bar that moves
    between the run that proposed a candidate and the run that checked it is not
    a bar. Here it is the candidate itself that must hold still: the same
    workspace, twice, byte for byte, or the number in the report belongs to one
    execution and not to the method."""
    _solver_source()
    _must_run(workspace)
    first = [f.read_bytes() for f in _deliverable_paths(workspace)]
    _must_run(workspace)
    second = [f.read_bytes() for f in _deliverable_paths(workspace)]

    for name, a, b in zip(_humanbrain().deliverables, first, second):
        assert a == b, (
            "%s differs between two runs on the same workspace. Whatever moved "
            "— a generator, a hash seed, a set iteration order — moves the "
            "correlation the judge reports with it, and the candidate cannot "
            "be re-checked." % name)


# --------------------------------------- 8. the staging loop, as it really runs

def test_the_staging_loop_withholds_exactly_the_key_and_the_solver_runs_on_the_rest(tmp_path):
    """The end-to-end claim, with `run_domain_task`'s own walk in the middle.

    The tests above assume a sandbox built to the staging rule. This one derives
    it: a seeded workspace WITH the answer key present, walked exactly as
    `run_domain_task` walks it — `rglob("*")`, files only, workspace-relative
    posix paths, withheld when the path is in `bench.answer_key` and staged
    otherwise — and then the solver run on nothing but what that walk staged.

    Two failures it is here to catch. An answer_key entry that never matches:
    an absolute path, a Windows separator, a name the generator does not
    actually write, and the loop withholds nothing while the report still lists
    a `withheld` field. And the mirror image: a rule that quietly withholds
    more than the key, which would starve the solver of the stimulus and read
    as a broken solver.

    The key is written as unreadable placeholder bytes. What is being tested is
    which PATHS the loop moves, and no response matrix needs to exist — or may
    be invented — for that."""
    hb = _humanbrain()
    _solver_source()

    seed_ws = _build_workspace(tmp_path / "seed", with_answer_key=True)
    run_ws = tmp_path / "run"
    run_ws.mkdir()

    withheld, staged = [], []
    for p in sorted(seed_ws.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(seed_ws).as_posix()
        if rel in hb.answer_key:
            withheld.append(rel)
            continue
        staged.append(rel)
        dst = run_ws / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(p.read_bytes())

    assert sorted(withheld) == sorted(hb.answer_key), (
        "the loop withheld %s against an answer_key of %s. A key entry that "
        "matches no staged path is withheld from nobody, silently, and the run "
        "report still carries a withheld field that reads as protection."
        % (sorted(withheld), sorted(hb.answer_key)))
    for rel in ("data/stimulus.json", "data/split.json", "data/train_features.npy",
                "data/heldout_features.npy", "code/run_solver.py"):
        assert rel in staged, (
            "%s did not reach the sandbox; staged: %s" % (rel, sorted(staged)))

    _must_run(run_ws)
    split = _split(run_ws)
    train_out, heldout_out = _deliverable_paths(run_ws)
    A = np.load(train_out, allow_pickle=False)
    B = np.load(heldout_out, allow_pickle=False)
    assert (A.shape[0], B.shape[0]) == (len(split["train_windows"]),
                                        len(split["heldout_windows"]))
    assert A.shape[1] == B.shape[1]
    for rel in hb.answer_key:
        assert not (run_ws / rel).exists(), (
            "%s appeared in the run workspace after the solver ran" % rel)
