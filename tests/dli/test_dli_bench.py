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


def test_coverage_names_what_is_not_built():
    """A suite covering less than its scale must say so rather than let a short
    list imply the rest passed."""
    absent = {k for k, v in COVERAGE.items() if v.startswith("NOT BUILT")}
    assert absent == {"DL4", "DL6", "DLOmega"}
    for lvl in absent:
        assert not any(g.level == lvl for g in GENERATORS.values())


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


def test_crosswalk_only_claims_cards_a_generator_can_pose():
    from ai4science.harness.agents.dli_bench import catalog
    cards = catalog.load()
    xw = catalog.crosswalk(cards)
    for c in cards:
        for key in xw[c.task_id]:
            g = GENERATORS[key]
            assert g.level == c.level and g.family == c.family
    # The levels with no generator must claim nothing.
    for c in cards:
        if c.level in ("DL4", "DL6", "DLOmega"):
            assert xw[c.task_id] == ()


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
