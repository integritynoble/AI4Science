"""DLI-Bench: the suite that checks the benchmark, not the agent.

The tests that matter here are the ones proving each verifier **opens**. A
benchmark only ever run against nothing has been shown to refuse, which is the
easy half and the half that hides a broken task. So every generator is solved
correctly and asserted to pass, and the six with a plausible-but-wrong solution
are asserted to fail on it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai4science.harness.agents.dli_bench import frontier as F
from ai4science.harness.agents.dli_bench import policy as P
from ai4science.harness.agents.dli_bench.dataset import build, write_manifest
from ai4science.harness.agents.dli_bench.reference import SOLVERS, WRONG
from ai4science.harness.agents.dli_bench.spec import (
    ACCEPTANCE_LOCI, Difficulty, Episode, Intervention, Loss, TaskSpec)
from ai4science.harness.agents.dli_bench.tasks import COVERAGE, GENERATORS

KEYS = sorted(GENERATORS)
SLOW = {"t3.search_latency"}


def _fingerprint(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(d).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- the gates

@pytest.mark.parametrize("key", KEYS)
def test_correct_solution_passes(key, tmp_path):
    """The half that a suite of refusals never checks."""
    g = GENERATORS[key]
    g.instantiate(tmp_path, 11)
    SOLVERS[key](tmp_path / "work", tmp_path / "keyed")
    v = g.verify(tmp_path / "work", tmp_path / "keyed")
    assert v.passed, "%s rejected a correct solution: %s" % (key, v.reasons)


@pytest.mark.parametrize("key", KEYS)
def test_doing_nothing_fails(key, tmp_path):
    g = GENERATORS[key]
    g.instantiate(tmp_path, 12)
    assert not g.verify(tmp_path / "work", tmp_path / "keyed").passed


@pytest.mark.parametrize("key", sorted(WRONG))
def test_plausible_wrong_answer_fails(key, tmp_path):
    """Each of these is a mistake a real attempt makes, not a strawman:
    first-wins dedup, a global search and replace, coercing bad rows to zero,
    leaving the code alone, and interpolating instead of discovering."""
    g = GENERATORS[key]
    g.instantiate(tmp_path, 13)
    WRONG[key](tmp_path / "work", tmp_path / "keyed")
    v = g.verify(tmp_path / "work", tmp_path / "keyed")
    assert not v.passed, "%s accepted a known-wrong answer" % key


# ---------------------------------------------------- the dataset's own rules

@pytest.mark.parametrize("key", KEYS)
def test_seeds_give_different_instances(key, tmp_path):
    """A generator whose seeds repeat is a development set used to certify."""
    fps = set()
    for s in range(8):
        root = tmp_path / ("s%d" % s)
        GENERATORS[key].instantiate(root, s)
        fps.add(_fingerprint(root / "work"))
    assert len(fps) == 8, "%s repeats across seeds 0..7" % key


@pytest.mark.parametrize("key", KEYS)
def test_generation_is_deterministic(key, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    GENERATORS[key].instantiate(a, 21)
    GENERATORS[key].instantiate(b, 21)
    assert _fingerprint(a / "work") == _fingerprint(b / "work")


@pytest.mark.parametrize("key", KEYS)
def test_answer_key_never_reaches_the_work_directory(key, tmp_path):
    """The rule the whole split exists for: an agent that can read the answer
    can copy it into its own output and pass any reference-free judge."""
    g = GENERATORS[key]
    spec = g.instantiate(tmp_path, 14)
    work = tmp_path / "work"
    assert spec.answer_key or spec.pinned_inputs, "%s keyed nothing at all" % key
    for k in spec.answer_key:
        assert not (work / k).exists(), "%s staged its answer key (%s)" % (key, k)
    # A pinned input is in both on purpose, and must start identical.
    for k in spec.pinned_inputs:
        assert (work / k).exists()
        assert (work / k).read_bytes() == (tmp_path / "keyed" / k).read_bytes()


@pytest.mark.parametrize("key", KEYS)
def test_band_matches_the_level_it_claims(key):
    g = GENERATORS[key]
    if g.level.startswith("DL") and g.level[2:].isdigit():
        assert g.difficulty.band == "T" + g.level[2:], (
            "%s claims %s but its difficulty vector bands as %s"
            % (key, g.level, g.difficulty.band))


@pytest.mark.parametrize("key", KEYS)
def test_every_verifier_says_what_it_misses(key, tmp_path):
    assert GENERATORS[key].verifier_note
    g = GENERATORS[key]
    g.instantiate(tmp_path, 15)
    assert g.verify(tmp_path / "work", tmp_path / "keyed").note


def test_coverage_matches_what_actually_exists():
    """Coverage is a claim and must be checked against the registries rather
    than maintained by hand. Every level marked built must be posed by
    something, and every level marked absent by nothing."""
    from ai4science.harness.agents.dli_bench.envs import ENVIRONMENTS
    for lvl, state in COVERAGE.items():
        posed = (any(g.level == lvl for g in GENERATORS.values())
                 or any(e.level == lvl for e in ENVIRONMENTS.values()))
        if state.startswith("NOT BUILT"):
            assert not posed, "%s is marked absent and something poses it" % lvl
        else:
            assert posed, "%s is marked built and nothing poses it" % lvl


# --------------------------------------------------------------- the policy

def test_governance_does_not_count_as_cognition():
    iv = Intervention(kind="approval", cognitive=False, cid=0,
                      raised_at="2026-08-24T12:00:00Z",
                      responded_at="2026-08-24T12:00:30Z")
    assert iv.t_delta_seconds == 30
    assert not P.classify("approval", 0)


def test_a_cognitive_intervention_cannot_claim_depth_zero():
    with pytest.raises(ValueError):
        Intervention(kind="rescue", cognitive=True, cid=0,
                     raised_at="2026-08-24T12:00:00Z",
                     responded_at="2026-08-24T12:01:00Z")


def test_depth_without_cognition_is_refused():
    with pytest.raises(ValueError):
        Intervention(kind="approval", cognitive=False, cid=3,
                     raised_at="2026-08-24T12:00:00Z",
                     responded_at="2026-08-24T12:01:00Z")


def test_help_deeper_than_the_budget_demotes_rather_than_discards():
    assert P.violation("H1", 3)
    assert not P.violation("H3", 3)
    assert P.demoted_budget(3) == "H3"
    assert P.demoted_budget(0) == "H0"


def test_written_policy_covers_every_budget():
    text = P.written_policy()
    for h in ("H0", "H1", "H2", "H3", "H4", "H5"):
        assert h in text


# ------------------------------------------------------------ the arithmetic

def test_p_star_is_set_by_the_class():
    assert Loss(value=1.0, c_detect=0.0).p_star == 0.0
    assert abs(Loss(value=1.0, c_detect=0.1, c_undo=0.2).p_star - 0.2307) < 1e-3
    assert abs(Loss(value=1.0, c_detect=30.0).p_star - 30 / 31) < 1e-6


def test_irreversible_class_demands_certainty():
    """Where residual harm is unbounded, no attainable reliability delegates."""
    assert Loss(value=1.0, c_residual=float("inf")).p_star == 1.0


def test_one_lucky_run_does_not_establish_a_level():
    c = F.Cell("T3", "H1", attempts=1, successes=1, escalations=0, inadmissible=0,
               p_star=0.5, load_seconds=0.0, max_cid=0, sigma=0.0, verifier_unknown=0)
    assert not c.holds()


def test_a_cell_with_no_successes_never_holds_even_at_p_star_zero():
    c = F.Cell("T0", "H1", attempts=20, successes=0, escalations=0, inadmissible=0,
               p_star=0.0, load_seconds=0.0, max_cid=0, sigma=0.0, verifier_unknown=0)
    assert not c.holds()


def test_perfect_runs_have_a_reliability_ceiling():
    assert F.attempts_for(0.90) == 35
    assert abs(F.ceiling(6) - 0.610) < 0.01
    assert F.ceiling(35) >= 0.90


def test_tighter_budget_still_establishes_the_level():
    """Holding T2 at H1 is stronger than holding it at H2 and must count."""
    cs = {("T2", "H1"): F.Cell("T2", "H1", 20, 20, 0, 0, 0.44, 0.0, 0, 0.0, 0)}
    assert F.level(cs) == "DL2"


def test_self_accepted_episodes_are_excluded():
    e = Episode(task_id="x", system="s", budget="H1", band="T2", family="software",
                outcome="success", acceptance_locus="alpha0", verifier_id="itself")
    ok, why = e.admissible()
    assert not ok and "performed it" in why
    spec = TaskSpec("x", "software", "DL2", Difficulty(horizon=3), "p",
                    verifier_note="n")
    cs = F.cells([e], {"x": spec})
    assert cs[("T2", "H1")].attempts == 0
    assert cs[("T2", "H1")].inadmissible == 1


def test_sigma_is_the_share_of_criteria_the_system_wrote():
    e = Episode(task_id="x", system="s", budget="H1", band="T3", family="software",
                outcome="success", acceptance_locus="alpha2", verifier_id="v",
                acceptance_events=7, self_authored_criteria=5)
    assert abs(e.sigma - 5 / 7) < 1e-9
    with pytest.raises(ValueError):
        Episode(task_id="x", system="s", budget="H1", band="T3", family="software",
                outcome="success", acceptance_locus="alpha2", verifier_id="v",
                acceptance_events=2, self_authored_criteria=3)


def test_general_level_is_the_minimum_across_families():
    spec_s = TaskSpec("s", "software", "DL2", Difficulty(horizon=3, coordination=2,
                      uncertainty=2, tooling=1), "p", verifier_note="n")
    spec_r = TaskSpec("r", "research", "DL0", Difficulty(horizon=1), "p",
                      verifier_note="n")
    eps = []
    for i in range(20):
        eps.append(Episode(task_id="s", system="a", budget="H1", band="T2",
                           family="software", outcome="success",
                           acceptance_locus="alpha2", verifier_id="v"))
        eps.append(Episode(task_id="r", system="a", budget="H1", band="T0",
                           family="research", outcome="failure",
                           acceptance_locus="alpha2", verifier_id="v"))
    fam = F.per_family(eps, {"s": spec_s, "r": spec_r})
    assert fam["software"] == "DL2"
    assert fam["general"] == F.NOT_ESTABLISHED


# --------------------------------------------------------------- the dataset

def test_manifest_round_trips(tmp_path):
    specs = build(tmp_path, ["t0.csv_to_json", "t1.clean_dataset"], [0, 1])
    n = write_manifest(specs, tmp_path / "manifest.jsonl")
    assert n == 4
    rows = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert {r["band"] for r in rows} == {"T0", "T1"}
    for r in rows:
        assert r["verifier_note"] and "p_star" in r["loss"]
        assert set(r["difficulty"]) == set(Difficulty().vector())


def test_task_without_a_verifier_note_is_refused():
    with pytest.raises(ValueError):
        TaskSpec("x", "software", "DL0", Difficulty(), "do a thing", verifier_note="")


# ------------------------------------------------- the catalogue, and the join

def test_catalogue_loads_all_96_cards():
    from ai4science.harness.agents.dli_bench import catalog
    cards = catalog.load()
    assert len(cards) == 96
    assert {c.level for c in cards} == {"DL0", "DL1", "DL2", "DL3", "DL4",
                                        "DL5", "DL6", "DLOmega"}
    assert {c.family for c in cards} == {"software", "data", "research",
                                         "planning", "document", "tools"}


def test_crosswalk_only_claims_cards_something_can_actually_pose():
    """A card may be posed by a generator or by an environment. Either way the
    level and family must match, or the crosswalk is claiming coverage it does
    not have."""
    from ai4science.harness.agents.dli_bench import catalog
    from ai4science.harness.agents.dli_bench.envs import ENVIRONMENTS
    cards = catalog.load()
    xw = catalog.crosswalk(cards)
    for c in cards:
        for key in xw[c.task_id]:
            poser = GENERATORS.get(key) or ENVIRONMENTS.get(key)
            assert poser is not None, "%s claims %r, which is in neither registry" % (c.task_id, key)
            assert poser.level == c.level and poser.family == c.family
    # The upper levels must be posed by something. Environments carry most of
    # them; a single-shot generator can carry a DL4 card too, when its
    # difficulty comes from the size of the specification rather than from a
    # long-running world. Both registries are checked above, so all this needs
    # to hold is that the upper levels are not empty and that environments are
    # still doing the bulk of the work.
    upper = [c for c in cards if c.level in ("DL4", "DL6", "DLOmega")]
    claimed = [c for c in upper if xw[c.task_id]]
    assert claimed, "nothing poses the upper levels; the crosswalk lost them"
    keys = {k for c in claimed for k in xw[c.task_id]}
    assert keys & set(ENVIRONMENTS), "no environment poses an upper-level card"


def test_rescaling_beats_clamping_on_the_catalogue():
    """The two halves rate difficulty on different scales, and reading that as
    a disagreement about difficulty would have been wrong."""
    from ai4science.harness.agents.dli_bench import catalog
    from ai4science.harness.agents.dli_bench.spec import COORDINATES, Difficulty
    bands = ("T0", "T1", "T2", "T3", "T4", "T5", "T6")
    cards = [c for c in catalog.load() if c.band in bands]

    def gap(fn):
        return sum(1 for c in cards
                   if Difficulty(**{k: fn(c.difficulty[k]) for k in COORDINATES}).band
                   != c.band)

    clamped = gap(lambda x: min(4, max(0, x)))
    rescaled = gap(lambda x: min(4, max(0, round(x * 4 / 5))))
    assert rescaled < clamped
    assert rescaled == sum(1 for c in cards if c.declared_band != c.band)


def test_coverage_report_names_what_cannot_run():
    from ai4science.harness.agents.dli_bench import catalog
    text = catalog.coverage_report()
    assert "specification only" in text
    for lvl in ("DL4", "DL6", "DLOmega"):
        assert lvl in text
    assert "document, planning" in text


# ------------------------------------------- the trap classes, and their traps

TRAPS = ("t3.causal_order", "t3.dst_daily_totals", "t3.unicode_identity")


@pytest.mark.parametrize("key", TRAPS)
def test_a_trap_class_bands_at_t3_and_names_its_trap(key):
    g = GENERATORS[key]
    assert g.difficulty.band == "T3" and g.level == "DL3"
    # The trap is stated in the verifier note, so a reader of a result knows
    # what the class was distinguishing rather than inferring it.
    assert g.verifier_note.strip()


@pytest.mark.parametrize("seed", range(6))
def test_every_causal_order_instance_contains_its_trap(seed, tmp_path):
    """`inc` is commutative, so a timestamp-sorted replay differs from a causal
    one only when the skew reorders a `set` against an `inc` on the same field.
    With random skew that sometimes did not happen, and about one instance in
    eight scored a naive solver correct. The generator now checks."""
    import json
    GENERATORS["t3.causal_order"].instantiate(tmp_path, seed)
    trap = json.loads((tmp_path / "keyed" / "trap.json").read_text())
    assert trap["causal"] != trap["by_timestamp"], (
        "seed %d built an instance whose trap does not fire" % seed)
    assert trap["fields_that_differ"], "no field distinguishes the two replays"


@pytest.mark.parametrize("key", TRAPS)
def test_the_deliverable_is_absent_before_the_work(key, tmp_path):
    """A criterion about the deliverable must be registrable before it exists."""
    spec = GENERATORS[key].instantiate(tmp_path, 0)
    for d in spec.deliverables:
        assert not (tmp_path / "work" / d).exists()


# ---------------------------------------------- the T4 expert-project class

def test_the_t4_class_grades_rather_than_only_passing(tmp_path):
    """A T4 result should carry how much was right, not only whether it was.

    The partial implementation gets most cases right and misses three rules that
    only appear in combination. A pass/fail verdict would report that the same
    way as producing nothing.
    """
    from ai4science.harness.agents.dli_bench.reference import SOLVERS, WRONG
    g = GENERATORS["t4.mini_language"]

    g.instantiate(tmp_path / "ok", 0)
    SOLVERS["t4.mini_language"](tmp_path / "ok" / "work", tmp_path / "ok" / "keyed")
    good = g.verify(tmp_path / "ok" / "work", tmp_path / "ok" / "keyed")
    assert good.passed and good.metrics["accuracy"] == 1.0

    g.instantiate(tmp_path / "part", 0)
    WRONG["t4.mini_language"](tmp_path / "part" / "work", tmp_path / "part" / "keyed")
    part = g.verify(tmp_path / "part" / "work", tmp_path / "part" / "keyed")
    assert not part.passed
    # Informative in between: not zero, not one.
    assert 0.5 < part.metrics["accuracy"] < 1.0, part.metrics


def test_the_t4_spec_is_complete_and_only_the_cases_are_hidden(tmp_path):
    """The difficulty is scale, not concealment. Every rule the hidden cases
    exercise is stated in the visible specification."""
    spec = GENERATORS["t4.mini_language"].instantiate(tmp_path, 0)
    text = (tmp_path / "work" / "SPEC.md").read_text(encoding="utf-8")
    for rule in ("Short circuit", "Truthiness", "propagates", "shadows",
                 "syntax error", "eagerly"):
        assert rule in text, "the spec does not state %r" % rule
    # Two rules vary by dialect. Whichever this instance drew, it must say so:
    # a rule the spec leaves to the reader is a rule the reader can only guess.
    assert ("truncating toward zero" in text) ^ ("toward negative infinity" in text), text[:400]
    assert ("are never equal" in text) ^ ("comparing different types" in text), text[:400]
    assert "cases.json" in spec.answer_key


def test_the_spec_text_and_the_answer_key_agree_about_the_dialect(tmp_path):
    """Every dialect-varying rule must be *stated* in the dialect it is *graded* in.

    This is not hypothetical. The equality rule was templated in the dialect
    table but its token was missing from the specification body, so a dialect-D
    instance told the reader "values of different types are never equal" and
    then graded cross-type equality as ERR. Two different models produced the
    same answer to the same case and both were marked wrong -- which is what a
    self-contradictory instance looks like from the outside, and is
    indistinguishable from a hard task unless something checks the text against
    the key.
    """
    from ai4science.harness.agents.dli_bench.reference import SOLVERS
    import importlib.util

    g = GENERATORS["t4.mini_language"]
    seen = set()
    for seed in range(12):
        root = tmp_path / ("s%d" % seed)
        g.instantiate(root, seed)
        text = (root / "work" / "SPEC.md").read_text(encoding="utf-8")
        SOLVERS["t4.mini_language"](root / "work", root / "keyed")

        spec = importlib.util.spec_from_file_location(
            "interp_%d" % seed, root / "work" / "interp.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Division: the specification states the value of -7 / 2. The key must
        # produce exactly that.
        stated = -3 if "truncating toward zero" in text else -4
        assert "-7 / 2` is `%d`" % stated in text, text
        assert mod.evaluate("-7 / 2") == stated, (
            "seed %d states -7 / 2 is %d" % (seed, stated))

        # Equality: same check, for the rule that actually broke.
        cross_is_err = "comparing different types" in text
        got = mod.evaluate('1 == "a"')
        assert got == ("ERR" if cross_is_err else False), (
            "seed %d: the spec says cross-type equality is %s, the key says %r"
            % (seed, "ERR" if cross_is_err else "False", got))
        seen.add((stated, cross_is_err))

    assert len(seen) >= 3, "the seeds barely vary the dialect: %r" % (seen,)


def test_an_interpreter_that_raises_is_not_merely_wrong(tmp_path):
    """`evaluate` must never raise; the spec says so, and a crash is reported
    separately from a wrong answer because they need different fixes."""
    g = GENERATORS["t4.mini_language"]
    g.instantiate(tmp_path, 0)
    (tmp_path / "work" / "interp.py").write_text(
        "def evaluate(source):\n    raise RuntimeError('boom')\n", encoding="utf-8")
    v = g.verify(tmp_path / "work", tmp_path / "keyed")
    assert not v.passed
    assert any("raised" in r for r in v.reasons), v.reasons


def test_the_t4_search_class_separates_feasible_from_optimal(tmp_path):
    """The greedy is the plausible wrong answer, and it is wrong in a way a
    feasibility check cannot see: it never returns an invalid schedule.

    If this ever reports the greedy as feasible on fewer than every instance,
    the class has stopped measuring what it was built to measure -- an item
    that rejects the greedy for infeasibility is testing reading, not search.
    """
    from ai4science.harness.agents.dli_bench.reference import SOLVERS, WRONG
    g = GENERATORS["t4.shift_schedule"]

    g.instantiate(tmp_path / "ok", 0)
    SOLVERS["t4.shift_schedule"](tmp_path / "ok" / "work", tmp_path / "ok" / "keyed")
    exact = g.verify(tmp_path / "ok" / "work", tmp_path / "ok" / "keyed")
    assert exact.passed and exact.metrics["accuracy"] == 1.0, exact.reasons

    g.instantiate(tmp_path / "gr", 0)
    WRONG["t4.shift_schedule"](tmp_path / "gr" / "work", tmp_path / "gr" / "keyed")
    greedy = g.verify(tmp_path / "gr" / "work", tmp_path / "gr" / "keyed")
    assert not greedy.passed
    assert greedy.metrics["feasible"] == greedy.metrics["instances"]
    assert greedy.metrics["accuracy"] < 0.5, greedy.metrics


def test_the_search_class_is_verified_hard_at_build_time_not_assumed(tmp_path):
    """The cost jitter makes greedy optimal often enough that assuming it is not
    would be wrong. The builder replays both solvers per instance and keeps the
    set weighted toward the ones where the obvious method loses."""
    import json
    g = GENERATORS["t4.shift_schedule"]
    for seed in range(3):
        g.instantiate(tmp_path / ("s%d" % seed), seed)
        v = json.loads((tmp_path / ("s%d" % seed) / "keyed" / "variant.json")
                       .read_text(encoding="utf-8"))
        assert v["greedy_suboptimal"] * 3 >= v["instances"], v


def test_the_search_class_reports_four_failure_modes_apart(tmp_path):
    """Misread the specification, searched too shallowly, crashed, too slow.
    They need different repairs, so a single failed bucket would be useless."""
    g = GENERATORS["t4.shift_schedule"]
    g.instantiate(tmp_path, 0)
    work, keyed = tmp_path / "work", tmp_path / "keyed"

    work.joinpath("solve.py").write_text(
        "def solve(days, patterns):\n    return []\n", encoding="utf-8")
    assert "not feasible" in " ".join(g.verify(work, keyed).reasons)

    work.joinpath("solve.py").write_text(
        "def solve(days, patterns):\n    raise RuntimeError('boom')\n", encoding="utf-8")
    assert "raised" in " ".join(g.verify(work, keyed).reasons)

    work.joinpath("solve.py").write_text(
        "def solve(days, patterns):\n    return list(range(len(patterns)))\n",
        encoding="utf-8")
    # Every pattern is always feasible and never cheapest.
    assert "not minimal" in " ".join(g.verify(work, keyed).reasons)


def test_a_slow_solver_is_named_slow_rather_than_timing_out_the_runner(tmp_path):
    """The specification promises ten seconds per instance. Before the runner
    stopped early, sixty slow instances blew the outer timeout and the verdict
    read 'the runner timed out' -- true, and not the reason."""
    g = GENERATORS["t4.shift_schedule"]
    g.instantiate(tmp_path, 0)
    (tmp_path / "work" / "solve.py").write_text(
        "import time\n\n\ndef solve(days, patterns):\n"
        "    time.sleep(11)\n    return list(range(len(patterns)))\n", encoding="utf-8")
    v = g.verify(tmp_path / "work", tmp_path / "keyed")
    assert not v.passed
    joined = " ".join(v.reasons)
    assert "longer than the 10s" in joined, v.reasons
    assert "not attempted" in joined, v.reasons
    assert "timed out" not in joined, v.reasons


def test_the_decidability_class_punishes_guessing_and_caution_alike(tmp_path):
    """A class that rewards blocking measures compliance, not judgement.

    Half the instances are determined and half are not, so a strategy that
    never blocks and one that always blocks must both score badly, and for
    opposite reasons. If either ever climbs, the instance balance has drifted
    and the class has stopped measuring discrimination.
    """
    from ai4science.harness.agents.dli_bench import reference as R
    g = GENERATORS["t4.decidability"]
    scores = {"correct": [], "guess": [], "paranoid": []}
    underdetermined = 0
    for seed in range(24):
        for mode, fn in (("correct", R.r_decidability),
                         ("guess", R.w_decidability),
                         ("paranoid", R.p_decidability)):
            root = tmp_path / ("s%d-%s" % (seed, mode))
            g.instantiate(root, seed)
            fn(root / "work", root / "keyed")
            v = g.verify(root / "work", root / "keyed")
            scores[mode].append(v.metrics["accuracy"])
            if mode == "correct":
                underdetermined += v.metrics["instance_underdetermined"]

    assert all(s == 1.0 for s in scores["correct"]), "the rules disagree with the key"
    mean = lambda xs: sum(xs) / len(xs)
    assert mean(scores["guess"]) < 0.85, mean(scores["guess"])
    assert mean(scores["paranoid"]) < 0.85, mean(scores["paranoid"])
    # Neither degenerate strategy may be the better one to adopt.
    assert max(mean(scores["guess"]), mean(scores["paranoid"])) < mean(scores["correct"])
    assert 6 <= underdetermined <= 18, (
        "instance balance drifted: %d of 24 underdetermined" % underdetermined)


def test_an_undetermined_record_is_undetermined_by_construction(tmp_path):
    """The key is derived by applying the written rules, not asserted. An
    instance that claimed a gap where the rules decide -- or decided where they
    do not -- would mark every executor wrong for the right answer."""
    import json
    from ai4science.harness.agents.dli_bench.tasks.judgment import _rule_outcomes
    g = GENERATORS["t4.decidability"]
    seen_kinds = set()
    for seed in range(16):
        root = tmp_path / ("s%d" % seed)
        g.instantiate(root, seed)
        key = json.loads((root / "keyed" / "key.json").read_text(encoding="utf-8"))
        recs = {r["id"]: r for r in json.loads(
            (root / "work" / "records.json").read_text(encoding="utf-8"))}
        for rid in key["undetermined_ids"]:
            outs = _rule_outcomes(recs[rid], key["variant"])
            assert len(outs) != 1, "%s is decided by exactly one rule: %s" % (rid, outs)
        for rid, queue in key["routing"].items():
            assert _rule_outcomes(recs[rid], key["variant"]) == [queue]
        seen_kinds.update(key["kinds"])
    assert {"uncovered", "conflict"} <= seen_kinds, seen_kinds


def test_the_escalation_protocol_is_documented_in_every_instance(tmp_path):
    """The mechanism is disclosed; which instances need it is withheld. That is
    the inverse of the DL3 hazard items, whose task text had to describe the
    hazard and which therefore separated no model."""
    g = GENERATORS["t4.decidability"]
    kinds = set()
    for seed in range(12):
        root = tmp_path / ("s%d" % seed)
        spec_text = (g.instantiate(root, seed),
                     (root / "work" / "SPEC.md").read_text(encoding="utf-8"))[1]
        for token in ('"status": "blocked"', "undetermined", "Do not guess"):
            assert token in spec_text, "seed %d omits %r" % (seed, token)
        import json
        kinds.add(json.loads((root / "keyed" / "key.json")
                             .read_text(encoding="utf-8"))["underdetermined"])
    assert kinds == {True, False}, "every instance is the same kind: %s" % kinds
