"""One agent per level, and the boundary each one refuses to cross.

A level claim has two halves and only one is usually checked. Holding the band
is the half everyone reports. Declining the band above is the half that makes
the number mean something -- an agent that attempts everything and reports what
it managed is describing its luck.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ai4science.harness.agents.delegation.bench_solver import (
    CarelessSolver, CompetentSolver)
from ai4science.harness.agents.delegation.certify import BY_BAND, certify
from ai4science.harness.agents.delegation.executor import SolverExecutor
from ai4science.harness.agents.delegation.interpreter import find as find_python
from ai4science.harness.agents.delegation.levels import (
    BANDS, SPECS, CriteriaOnly, LevelAgent)

LEVELS = ("DL0", "DL1", "DL2", "DL3")


@pytest.mark.parametrize("level", LEVELS)
def test_each_level_holds_its_own_band(level):
    r = certify(level, seeds=(0, 1), use_claude=False)
    assert r.in_band, "%s certified against nothing" % level
    assert r.held == len(r.in_band), "%s: %s" % (level, r.report())


@pytest.mark.parametrize("level", LEVELS)
def test_each_level_refuses_the_band_above(level):
    r = certify(level, seeds=(0,), use_claude=False)
    assert r.refusals
    for band, refused, why in r.refusals:
        assert refused, "%s attempted %s instead of declining it" % (level, band)
        assert level in why and "Refusing" in why


@pytest.mark.parametrize("level", LEVELS)
def test_certification_requires_both_halves(level):
    r = certify(level, seeds=(0, 1), use_claude=False)
    assert r.passed


def test_a_higher_level_accepts_lower_bands():
    """The refusal runs one way only: DL3 given a T0 task is fine."""
    a = LevelAgent("DL3", [])
    for band in ("T0", "T1", "T2", "T3"):
        assert a.would_accept(band)[0]
    assert not a.would_accept("T4")[0]


def test_the_criteria_source_can_never_be_chosen_to_do_the_work():
    """The bug this pins: unwrapped, the router picked the criteria source as an
    executor and its solver did the task carelessly, failing DL0 and DL1 for a
    reason that had nothing to do with either level."""
    src = CriteriaOnly(SolverExecutor("criteria", CarelessSolver("t2.pipeline")))
    assert src.capabilities()["cost"] >= 1e9
    with pytest.raises(RuntimeError):
        src.execute(None, Path("."), ())


def test_levels_are_ordered_and_each_declares_its_limits():
    seen = []
    for lvl in LEVELS:
        s = SPECS[lvl]
        seen.append(BANDS.index(s.highest_band))
        assert s.human_supplies and s.agent_supplies and s.note
    assert seen == sorted(seen), "the levels are not ordered by band"


def test_only_dl3_routes_and_only_dl2_up_derive_criteria():
    assert not SPECS["DL0"].derives_criteria
    assert not SPECS["DL1"].derives_criteria
    assert SPECS["DL2"].derives_criteria and SPECS["DL3"].derives_criteria
    assert not SPECS["DL2"].routes and SPECS["DL3"].routes
    assert SPECS["DL0"].max_attempts == 1 and SPECS["DL1"].max_attempts == 1


def test_every_band_used_for_certification_has_a_class():
    for lvl in LEVELS:
        band = SPECS[lvl].highest_band
        assert BY_BAND.get(band), "%s claims %s and nothing poses it" % (lvl, band)


def test_an_interpreter_is_resolvable_and_says_why():
    py, why = find_python()
    assert py and why
    assert Path(py).exists()


# ------------------------------------------------------- the v0.2 dataset

v02 = pytest.importorskip("ai4science.harness.agents.delegation.dataset_v02")


def _cards():
    try:
        return v02.load()
    except FileNotFoundError:
        pytest.skip("v0.2 dataset not present on this machine")


def test_v02_loads_all_four_strata():
    cards = _cards()
    assert len(cards) == 180
    strata = {c.stratum for c in cards}
    assert strata == {"ladder", "kappa_cross", "budget_cross", "probe"}


def test_a_stated_rho_beats_the_zero_to_five_rating():
    """Rating 5 covers both an unbounded class and one at rho=30. Collapsing
    them made the agent refuse three classes it should have attempted."""
    cards = {c.task_id: c for c in _cards()}
    unbounded = [c for c in cards.values()
                 if c.stratum == "kappa_cross" and c.risk == 5 and c.unbounded]
    finite = [c for c in cards.values()
              if c.stratum == "kappa_cross" and c.risk == 5 and not c.unbounded]
    assert unbounded and finite, "the two kinds of risk=5 are both needed here"
    for c in unbounded:
        assert c.contract().p_star >= 1.0
    for c in finite:
        p = c.contract().p_star
        assert 0.5 < p < 1.0, "%s: p*=%.3f" % (c.task_id, p)


def test_the_agent_agrees_with_the_dataset_about_what_is_undelegable():
    kx = [c for c in _cards() if c.stratum == "kappa_cross"]
    assert kx
    for c in kx:
        refuses = c.contract().p_star >= 1.0
        assert refuses == c.must_be_refused, (
            "%s: dataset says %s, agent says %s"
            % (c.task_id, "refuse" if c.must_be_refused else "attempt",
               "refuse" if refuses else "attempt"))


def test_a_low_band_class_can_still_be_undelegable():
    """The non-closure result, from the dataset's own cards: a T1 task -- one
    operation -- that no reliability delegates."""
    kx = [c for c in _cards() if c.stratum == "kappa_cross"]
    hard_and_small = [c for c in kx
                      if c.band in ("T0", "T1") and c.contract().p_star >= 1.0]
    assert hard_and_small, "no low-band undelegable class; the crossing is the point"


# ------------------------------------------------------- the harness ladder

def test_each_rung_is_a_strict_superset_of_the_one_below():
    """Without this, a between-rung difference is attributable to nothing."""
    from ai4science.harness.agents.delegation.ladder import LADDER
    prev = None
    for r in LADDER:
        if prev is not None:
            assert r.max_attempts >= prev.max_attempts
            assert r.acceptance >= prev.acceptance
            assert r.reversible >= prev.reversible
            assert r.routes >= prev.routes
            assert set(prev.mechanisms).isdisjoint(r.mechanisms), (
                "%s repeats a mechanism from %s" % (r.name, prev.name))
        prev = r


def test_hg0_has_no_acceptance_step():
    """It is the configuration a contemporary leaderboard measures: one attempt,
    and whatever comes back is the answer."""
    from ai4science.harness.agents.delegation.ladder import BY_NAME
    assert not BY_NAME["HG0"].acceptance
    assert BY_NAME["HG0"].max_attempts == 1
    assert BY_NAME["HG1"].acceptance


def test_a_di_is_blind_to_acceptance():
    """The paper's central claim, as arithmetic.

    Two rungs with the same success surface score the same, however differently
    they behaved about accepting wrong work -- because A_DI is defined on
    P(success) and acceptance does not change it.
    """
    from ai4science.harness.agents.delegation.ladder import delegation_surface_score
    surface = {("T0", "H1"): 1.0, ("T1", "H1"): 0.5, ("T2", "H1"): 1.0}
    assert delegation_surface_score(surface) == delegation_surface_score(dict(surface))


def test_the_net_surface_separates_what_the_gross_one_cannot():
    """Same pass rates, different false-completion rates, different score."""
    import json
    import subprocess
    import sys
    from pathlib import Path
    tool = Path("/home/spiritai/pwm/sarsi_intelligence_level/dataset/"
                "HIL_Benchmark_Library_v0_2/tools/score_hlis.py")
    if not tool.exists():
        pytest.skip("library v0.2 not present on this machine")
    surface = json.dumps({"T0": {"H1": 1.0}, "T1": {"H1": 0.5}})

    def run(fc, gross):
        cmd = [sys.executable, str(tool), "--components", '{"DI":0}',
               "--surface", surface, "--false-completion",
               json.dumps({"T1": {"H1": fc}}), "--rho", "1.0"]
        if gross:
            cmd.append("--gross")
        return json.loads(subprocess.run(cmd, capture_output=True,
                                         text=True).stdout)["HLIS"]

    # HG0-like: the failures were handed back as done. HG1-like: held back.
    assert run(0.5, gross=True) == run(0.0, gross=True), "gross must be blind"
    assert run(0.5, gross=False) < run(0.0, gross=False), "net must separate them"


def test_a_criteria_provider_is_not_in_the_routing_pool():
    """It crashed a live run: every real executor was excluded as incapable, and
    the least-bad remaining option was the criteria source."""
    from ai4science.harness.agents.delegation.executor import CompetenceModel, SolverExecutor
    from ai4science.harness.agents.delegation.levels import CriteriaOnly
    from ai4science.harness.agents.delegation.router import Router
    real = SolverExecutor("real", CarelessSolver("t2.pipeline"))
    pool = [CriteriaOnly(SolverExecutor("criteria", CarelessSolver("t2.pipeline"))), real]
    r = Router(pool, CompetenceModel())
    assert r.executors == [real]
    assert len(r.providers) == 1
    # And with the only real executor excluded, it returns nothing rather than
    # the provider.
    from ai4science.harness.agents.delegation.contract import read_task
    assert r.choose(read_task("t", "x"), "cls", exclude=["real"]).executor is None


# ------------------------------------------------------------- paired design

def test_the_paired_design_shares_one_verdict_between_the_rungs():
    """The property that makes Proposition 1 controlled rather than observed.

    Under pairing the two rungs read one set of artifacts and one verifier
    verdict, so their gross surfaces are identical by construction. A non-zero
    difference would mean a defect in the measuring harness, not a fact about
    acceptance.
    """
    from ai4science.harness.agents.delegation.paired import (
        PairedEpisode, _surface, _weighted)
    # Each band needs a mixed outcome for the subtraction to bite. A band whose
    # pass rate equals its false-completion rate nets to zero under both
    # scorings, because the net surface floors at zero -- see the note in the
    # paper: a band where everything wrong was delivered scores nothing, which
    # is correct and means the metric saturates at the bottom.
    eps = [PairedEpisode("t1.a", "T1", 0, True, True, 2, 1.0),
           PairedEpisode("t1.b", "T1", 1, False, False, 2, 1.0),
           PairedEpisode("t2.c", "T2", 0, True, True, 2, 1.0),
           PairedEpisode("t2.d", "T2", 1, False, True, 2, 1.0)]
    surface = _surface(eps)
    # One surface, so one gross figure however the rungs treated the failures.
    assert _weighted(surface) == _weighted(surface)

    by = {}
    for e in eps:
        by.setdefault(e.band, []).append(e)
    fc0 = {b: sum(x.hg0_false_completion for x in v) / len(v) for b, v in by.items()}
    fc1 = {b: sum(x.hg1_false_completion for x in v) / len(v) for b, v in by.items()}
    # HG0 delivers every failure; HG1 delivers only the ones it accepted.
    assert _weighted(surface, fc0) < _weighted(surface, fc1)


def test_the_four_paired_outcomes_are_mutually_exclusive():
    from ai4science.harness.agents.delegation.paired import PairedEpisode
    cases = [(True, True), (True, False), (False, True), (False, False)]
    for verdict, accepted in cases:
        e = PairedEpisode("k", "T1", 0, verdict, accepted, 1, 0.0)
        flags = [e.hg1_false_completion, e.hg1_held_back, e.hg1_false_rejection]
        assert sum(flags) <= 1, "an episode landed in two outcome buckets"
        # HG0 has no acceptance step, so a wrong result is always delivered.
        assert e.hg0_false_completion == (not verdict)
