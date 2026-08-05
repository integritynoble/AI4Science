"""The governor's research agents, and the refusals that make them safe to leave running.

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

def test_every_agent_builds_and_forbids_the_same_three():
    """Counted against the registry, not against a number written here.

    This asserted `len(agents) == 6`. It is a test about forbidden substrates,
    and adding a seventh agent broke it — which tells you nothing about whether
    the seventh forbids the right things. The registry is the source of how many
    there are."""
    agents = build_all()
    assert set(agents) == set(NAMES)
    assert len(agents) == len(NAMES)
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


def test_they_ship_with_transfer_candidates():
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


# ------------------------------------------------- generalist and specialist

def _coverage(*names):
    from ai4science.harness.agents.research_agents.coverage import Coverage, load_known
    k = load_known()
    return Coverage([k[n] for n in names])


def test_the_specialist_takes_the_work_when_both_are_installed():
    cov = _coverage("imaging", "low-dose-ct")
    assert cov.route("low-dose").agent == "low-dose-ct"
    assert cov.route("sci-cassi").agent == "imaging", "outside the specialist's field"


def test_the_generalist_takes_it_when_the_specialist_is_not_installed():
    assert _coverage("imaging").route("low-dose").agent == "imaging"


def test_each_specialist_stands_alone():
    """Installed by itself, with no generalist anywhere."""
    for name, sub in (("low-dose-ct", "photon-counting"),
                      ("medical-physics", "brachytherapy"),
                      ("pill-camera", "localisation")):
        assert _coverage(name).route(sub).agent == name


def test_uninstalling_the_specialist_does_not_widen_the_generalist():
    """The safety property. If imaging could do CT work under its own looser
    charter, the way round every gate would be to uninstall the specialist."""
    from ai4science.harness.agents.research_agents.charter import CharterViolation
    alone = _coverage("imaging")
    # imaging never declared this substrate, so its own charter is silent...
    build("imaging").charter.check("method")
    with pytest.raises(CharterViolation):
        build("imaging").charter.check("dose_equivalence_framework")
    # ...and on CT work it is forbidden by inheritance, with the owner named.
    with pytest.raises(CharterViolation) as e:
        alone.check("imaging", "low-dose", "dose_equivalence_framework")
    assert "inherited from low-dose-ct" in str(e.value)


def test_the_clinical_refusal_travels_to_whoever_does_the_work():
    """medical-physics refuses to export a deliverable plan. imaging doing
    imaging-physics work carries that refusal too, uninstalled or not."""
    cov = _coverage("imaging")
    rs = cov.refusals_for("imaging", "imaging-physics")
    assert any("physicist signs" in r for r in rs)
    assert any(r.startswith("[medical-physics]") for r in rs)


def test_a_generalist_on_capsule_work_carries_the_seed_rule():
    rs = _coverage("imaging").refusals_for("imaging", "lesion-detection")
    assert any("seed variance is not an improvement" in r for r in rs)


def test_a_scope_statement_does_not_travel_but_a_binding_refusal_does():
    """imaging says it does not interpret a scene — a boundary of its own role.
    Handed to pill-camera, whose whole purpose is interpreting capsule frames, it
    would forbid the specialist's core function. Binding refusals travel; scope
    statements do not, and the split is what makes symmetric inheritance safe."""
    rs = _coverage("imaging", "pill-camera").refusals_for("pill-camera",
                                                          "lesion-detection")
    assert any("seed variance" in r for r in rs), "its own, undiluted"
    assert not any("does not interpret" in r for r in rs), "scope did not travel"
    assert any(r.startswith("[imaging]") for r in rs), "binding ones did"


def test_a_scope_note_is_still_shown_to_the_owner():
    assert "not its job:" in build("imaging").charter.describe()


def test_the_arrangement_audits_clean():
    """A non-empty audit is a design error, not a runtime condition."""
    assert _coverage("imaging", "low-dose-ct", "medical-physics",
                     "pill-camera", "drug-design", "cancer").audit() == []


def test_nothing_installed_for_a_subfield_says_so():
    from ai4science.harness.agents.research_agents.coverage import NoAgentForWork
    with pytest.raises(NoAgentForWork):
        _coverage("cancer").route("ptychography")


# ------------------------------------------------------- peers, not hierarchies

def test_cancer_and_drug_design_stand_alone_and_overlap():
    assert _coverage("cancer").route("genomics").agent == "cancer"
    assert _coverage("drug-design").route("docking").agent == "drug-design"
    both = _coverage("cancer", "drug-design")
    assert both.route("drug-response").agent == "cancer"        # cancer owns it
    assert both.route("target-id").agent == "drug-design"       # drug-design owns it


def test_peers_inherit_each_others_refusals_in_both_directions():
    """The reason inheritance cannot be based on which field is smaller. Neither
    of these is inside the other, and both refusals have to bind."""
    cov = _coverage("cancer", "drug-design")
    # drug-design doing oncology work carries cancer's patient refusal
    rs = cov.refusals_for("drug-design", "drug-response")
    assert any("never advises a patient" in r for r in rs)
    # cancer doing molecule work carries drug-design's harm refusal
    rs = cov.refusals_for("cancer", "target-id")
    assert any("does not design, screen for, or optimise toward toxicity" in r
               for r in rs)


def test_a_peer_cannot_be_escaped_by_uninstalling_it():
    from ai4science.harness.agents.research_agents.charter import CharterViolation
    alone = _coverage("drug-design")            # cancer not installed at all
    rs = alone.refusals_for("drug-design", "drug-response")
    assert any("never advises a patient" in r for r in rs)
    with pytest.raises(CharterViolation):
        alone.check("drug-design", "drug-response", "patient_record")


def test_cancer_doing_dose_outcome_work_carries_the_physicist_rule():
    rs = _coverage("cancer").refusals_for("cancer", "outcome-modelling")
    assert any("physicist signs" in r for r in rs)


def test_every_shared_subfield_has_exactly_one_owner():
    """A subfield two agents cover and nobody owns routes by a coin toss dressed
    as a decision. The audit refuses to let that ship."""
    assert _coverage(*NAMES).audit() == []


def test_a_tie_is_reported_rather_than_hidden():
    from ai4science.harness.agents.research_agents.coverage import Coverage
    from ai4science.harness.agents.research_agents.charter import Charter
    a = Charter(name="a", field="f", subfields=("x", "y"), may_improve=("method",))
    b = Charter(name="b", field="f", subfields=("x", "z"), may_improve=("method",))
    got = Coverage([a, b]).route("x")
    assert got.ambiguous and got.tied_with == ("b",)
    assert "name the agent you want" in got.because


def test_owning_what_you_do_not_cover_is_refused():
    from ai4science.harness.agents.research_agents.charter import Charter
    with pytest.raises(ValueError):
        Charter(name="x", field="f", subfields=("a",), owns=("b",),
                may_improve=("method",))
