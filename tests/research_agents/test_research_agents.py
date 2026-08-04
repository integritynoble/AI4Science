"""The six research agents, and the refusals that make them safe to leave running.

Most of these tests are about what the agents will NOT do. That is not defensive
padding: an autonomous research agent's failure mode is not a crash, it is a
plausible paper, and every check below corresponds to a specific way a confident
wrong result gets manufactured overnight.
"""
from __future__ import annotations

import pytest

from ai4science.harness.agents.research_agents import (
    Budget, BudgetExhausted, Charter, CharterViolation, Claim, Dimension,
    FieldMap, FORBIDDEN, Improvement, NAMES, SeedResult, SelfModel, Switch,
    Unobserved, build, build_all, no_change,
)
from ai4science.harness.agents.research_agents.fieldmap import UNREPLICATED, UNTRIED


# ------------------------------------------------------------------ the charter

def test_all_six_build_and_forbid_the_same_three():
    agents = build_all()
    assert set(agents) == set(NAMES) and len(agents) == 6
    for name, a in agents.items():
        for substrate in FORBIDDEN:
            assert substrate in a.charter.never_touch, name
            with pytest.raises(CharterViolation):
                a.charter.check(substrate)


def test_a_charter_cannot_be_built_that_scores_itself():
    """The class refuses to represent an agent allowed to edit its own scorer —
    there is no argument that removes benchmark/metric/verifier."""
    ch = Charter(name="x", field="f", subfields=("s",), may_improve=("method",))
    assert set(FORBIDDEN) <= set(ch.never_touch)
    with pytest.raises(ValueError):
        Charter(name="x", field="f", subfields=("s",), may_improve=())
    with pytest.raises(ValueError):
        Charter(name="x", field="f", subfields=("s",), may_improve=("benchmark",))


def test_the_refusal_says_why_not_just_no():
    """A refusal a researcher cannot explain to the owner is one they will route
    around."""
    a = build("imaging")
    with pytest.raises(CharterViolation) as e:
        a.charter.check("metric")
    assert "what better means" in str(e.value)


def test_imaging_may_not_touch_the_forward_model():
    a = build("imaging")
    a.charter.check("method")                      # allowed
    with pytest.raises(CharterViolation):
        a.charter.check("forward_model")


def test_medical_physics_may_not_touch_clinical_constraints():
    a = build("medical-physics")
    with pytest.raises(CharterViolation):
        a.charter.check("clinical_constraints")
    with pytest.raises(CharterViolation):
        a.charter.check("approval_state")


def test_publishing_needs_a_grant_naming_that_act():
    a = build("cancer")
    with pytest.raises(CharterViolation):
        a.charter.check_outward("publish")
    with pytest.raises(CharterViolation):
        a.charter.check_outward("submit", granted=("publish",))   # not the same act
    a.charter.check_outward("publish", granted=("publish",))       # fine


def test_an_agent_is_not_scored_on_a_benchmark_it_authored():
    a = build("pill-camera")
    a.charter.scored_on("someone-else")
    with pytest.raises(CharterViolation):
        a.charter.scored_on("pill-camera")


# ---------------------------------------------------------------- the self-model

def test_unmeasured_is_reported_as_unmeasured_not_zero():
    """A 0.0 in a table reads as *measured and bad*. Never run is a different
    fact, and only one of them is true."""
    a = build("low-dose-ct")
    r = a.self_model.report()
    assert "unmeasured" in r
    assert "0.0" not in r
    with pytest.raises(Unobserved):
        a.self_model.value("detectability")


def test_a_number_without_evidence_is_not_an_observation():
    a = build("low-dose-ct")
    with pytest.raises(ValueError):
        a.self_model.observe("fidelity", 38.2, evidence="  ")


def test_the_limits_line_cannot_be_omitted():
    a = build("drug-design")
    assert "limits:" in a.self_model.report()
    with pytest.raises(ValueError):
        SelfModel("x", (Dimension("k", "K", "measured somehow"),), limits=())


def test_fidelity_without_detectability_is_flagged():
    """The CT failure this design most fears: a denoiser raises PSNR by smoothing
    away the lesion the scan was for."""
    a = build("low-dose-ct")
    a.self_model.observe("fidelity", 38.2, evidence="paired full-dose, vendor A")
    assert a.self_model.paired_gaps()
    assert "detectability" in a.self_model.report()
    a.self_model.observe("detectability", 0.81, evidence="CHO, inserted signals")
    assert not a.self_model.paired_gaps()


def test_reading_the_self_model_grants_nothing():
    a = build("imaging")
    with pytest.raises(NotImplementedError):
        a.self_model.authority()


# -------------------------------------------------------------------- the budget

def test_the_loop_stops_rather_than_asking_for_more():
    b = Budget("x", units=4.0)
    b.spend(3.0, what="one ablation")
    with pytest.raises(BudgetExhausted) as e:
        b.spend(2.0, what="a training run")
    assert "The loop stops here" in str(e.value)
    assert b.remaining() == pytest.approx(1.0), "a refused spend costs nothing"


def test_there_is_no_extend():
    b = Budget("x", units=1.0)
    assert not hasattr(b, "extend")
    assert not hasattr(b, "raise_to")


def test_the_agent_cannot_turn_itself_on():
    s = Switch("imaging")
    assert not s.on
    with pytest.raises(PermissionError):
        s.agent_turn_on()
    with pytest.raises(PermissionError):
        s.require_on()
    s.owner_turn_on(Budget("imaging", units=6.0))
    assert s.on and s.require_on().remaining() == 6.0


def test_an_exhausted_budget_turns_the_switch_off_by_itself():
    s = Switch("x")
    b = Budget("x", units=1.0)
    s.owner_turn_on(b)
    b.spend(1.0, what="everything")
    assert not s.on, "exhausted means off, without anyone intervening"


# ------------------------------------------------------------------ the field map

def test_a_claim_read_in_a_paper_is_not_a_fact():
    m = FieldMap("x")
    c = m.read_from_literature("k", "method M beats N", source="a 2026 paper")
    assert c.trusted is False and c.status == UNREPLICATED
    with pytest.raises(PermissionError):
        m.believe("k")


def test_a_failed_reproduction_is_kept_not_deleted():
    """A published number that does not reproduce is one of the most valuable
    things an agent in these fields can report."""
    m = FieldMap("x")
    m.read_from_literature("k", "M beats N by 2 dB", source="paper")
    c = m.reproduced("k", evidence="0.1 dB, same protocol", agrees=False)
    assert c.trusted is False
    assert "did NOT reproduce" in c.note
    assert "k" in m.claims


def test_next_work_prefers_reproduction_over_novelty():
    m = FieldMap("x", [
        Claim(key="new", statement="untried crossing", source="table",
              status=UNTRIED, subfield="a", from_subfield="b", at=1.0),
        Claim(key="old", statement="unreplicated claim", source="paper",
              status=UNREPLICATED, subfield="a", at=2.0),
    ])
    assert m.next_work().key == "old"


def test_the_six_ship_with_transfer_candidates():
    """Each agent should already know somewhere its field has not looked."""
    have = {n: build(n).field_map for n in NAMES}
    assert sum(len(m.transfer_candidates()) for m in have.values()) >= 4


# ----------------------------------------------------------------- an improvement

def _imp(**kw):
    base = dict(agent="pill-camera", candidate="c1", metric="macro-AUC",
                baseline_reproduced=True, held_out=True, comparisons=1,
                mechanism="haemoglobin absorption is visible in RGB",
                verifier_passed=True)
    base.update(kw)
    return Improvement(**base)


def test_an_effect_smaller_than_the_seed_spread_is_refused():
    """+0.023 against a ±0.027 spread is the seed lottery, not a result."""
    imp = _imp(seeds=[SeedResult(s, 0.760, 0.760 + d) for s, d in
                      zip(range(6), (0.05, -0.02, 0.04, -0.03, 0.02, 0.08))])
    assert imp.smaller_than_noise is True
    assert not imp.survives()
    assert any("seed lottery" in f for f in imp.failures())


def test_a_clean_effect_survives():
    imp = _imp(seeds=[SeedResult(s, 0.760, 0.760 + d) for s, d in
                      zip(range(6), (0.05, 0.048, 0.052, 0.049, 0.051, 0.05))])
    assert imp.survives(), imp.failures()


def test_one_seed_is_not_evidence():
    imp = _imp(seeds=[SeedResult(0, 0.76, 0.81)])
    assert any("fewer than two seeds" in f for f in imp.failures())


def test_every_seed_appears_in_the_report_including_the_bad_ones():
    imp = _imp(seeds=[SeedResult(0, 0.76, 0.79), SeedResult(1, 0.76, 0.74)])
    r = imp.report()
    assert "seed 0" in r and "seed 1" in r
    assert "-0.02" in r.replace("−", "-")
    assert "1/2 positive" in imp.verdict()["seeds"]


def test_trying_many_things_needs_a_corrected_statistic():
    imp = _imp(comparisons=12, corrected_p=None,
               seeds=[SeedResult(s, 0.76, 0.81) for s in range(4)])
    assert any("no corrected statistic" in f for f in imp.failures())


def test_a_number_with_no_mechanism_is_a_lead_not_a_finding():
    imp = _imp(mechanism="", seeds=[SeedResult(s, 0.76, 0.81) for s in range(4)])
    assert any("no mechanism" in f for f in imp.failures())


def test_the_verifier_must_have_actually_judged_it():
    imp = _imp(verifier_passed=None,
               seeds=[SeedResult(s, 0.76, 0.81) for s in range(4)])
    assert any("has not judged" in f for f in imp.failures())


def test_a_baseline_from_a_paper_is_not_a_baseline():
    imp = _imp(baseline_reproduced=False,
               seeds=[SeedResult(s, 0.76, 0.81) for s in range(4)])
    assert any("never reproduced here" in f for f in imp.failures())


def test_no_change_is_a_result_not_a_failure():
    out = no_change("imaging", because="no candidate cleared the validation set")
    assert out["candidate"] == "no-change"
    assert "not a failure of the run" in out["note"]


# --------------------------------------------------------------------- the specs

def test_the_three_new_specs_load_and_are_market_visible():
    from ai4science.harness.agents import registry as reg
    reg.reload()
    for name in ("low-dose-ct", "medical-physics", "pill-camera"):
        spec = reg.get(name)
        assert spec is not None, name
        assert spec.tier == "science" and spec.category == "specific"
        assert "spend" in spec.approval_required_for


def test_medical_physics_requires_approval_to_export_a_plan():
    from ai4science.harness.agents import registry as reg
    reg.reload()
    assert "plan-export" in reg.get("medical-physics").approval_required_for
