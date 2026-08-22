"""What an episode is allowed to become. [plan v3 §M5.2-§M5.4, §11.9]

The trigger→lesson pipeline has one narrow place it must not shortcut:

    trigger -> episode -> candidate lesson -> consolidation -> evidence -> promotion

A single surprising episode is an episode. It is not a truth, and a system that
lets one become one learns superstitions at exactly the rate it meets
coincidences. So promotion needs repeated support, contradictions block it, and
a procedure needs its preconditions, its tests, its postconditions and its
rollback before it may run — checked here rather than trusted from the record
that claims them.
"""
import pytest

from ai4science.harness.agents.sarsi import (consolidate, ledger, memory,
                                             registry as reg, semantic)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["sarsi-worker"]


def _fail(config, agent, n, summary="the export timed out"):
    for _ in range(n):
        memory.record(config, agent, "refusal", summary,
                      "detail: the export timed out after 60s")


def _skill_candidate(config, agent, **over):
    rec = {"schema_version": 1, "skill_id": "skl_test", "version": 1,
           "op": "propose", "status": "candidate", "agent_id": agent.id,
           "description": "drain then re-run",
           "preconditions": ["the queue exists"],
           "tests": ["pytest tests/test_export.py"],
           "postconditions": ["the queue length reads 0"],
           "rollback": "restore the queue snapshot",
           "evidence_refs": ["ep_1", "ep_2", "ep_3"],
           "scope": ["global"]}
    rec.update(over)
    ledger.append(config, "skills", rec)
    return rec["skill_id"]


# ── one episode is not a truth ───────────────────────────────────────────────

def test_a_single_surprising_episode_stays_episodic(config, agent):
    _fail(config, agent, 1)
    report = consolidate.run(config, agent)
    assert report["episodes_read"] >= 1
    assert report["semantic_candidates"] == []


def test_a_repeated_supported_pattern_can_become_a_candidate(config, agent):
    _fail(config, agent, consolidate.MIN_SUPPORT_FOR_CANDIDATE)
    report = consolidate.run(config, agent)
    assert report["semantic_candidates"]


def test_and_a_candidate_is_not_an_active_truth(config, agent):
    """It is proposed, with its evidence. Something else confirms it."""
    _fail(config, agent, consolidate.MIN_SUPPORT_FOR_CANDIDATE)
    consolidate.run(config, agent)
    actives = semantic.active_entries(config, agent)
    assert all(e.get("status") != "active" or "timed out" not in e.get("statement", "")
               for e in actives)


def test_contradictory_evidence_blocks_a_silent_promotion(config, agent):
    """An active entry that says the opposite stops the candidate. A store
    that holds both without noticing is not a memory, it is a pile.

    The incumbent check is lexical and says so — never/always, do/do not. It
    is a floor, not a proof: what it catches must not be promoted silently,
    and what it misses still needs a person."""
    semantic.record(config, agent, "the export always drains before it runs",
                    kind="invariant", scope=["global"], provenance=["owner"])
    _fail(config, agent, consolidate.MIN_SUPPORT_FOR_CANDIDATE,
          summary="the export never drains before it runs")
    report = consolidate.run(config, agent)
    assert report["skipped_contradictions"] >= 1


# ── a procedure needs more than a good run ───────────────────────────────────

def test_a_complete_candidate_can_be_promoted(config, agent):
    sid = _skill_candidate(config, agent)
    out = consolidate.promote_skill(config, agent, sid, sandbox_exit_code=0)
    assert out["status"] == "active"
    assert [s["skill_id"] for s in consolidate.active_skills(config, agent)] == [sid]


@pytest.mark.parametrize("missing", ["preconditions", "tests", "postconditions",
                                     "rollback", "evidence_refs"])
def test_every_precondition_of_promotion_is_actually_required(config, agent, missing):
    sid = _skill_candidate(config, agent, skill_id=f"skl_{missing}", **{missing: []
                           if missing != "rollback" else ""})
    with pytest.raises(consolidate.SkillPromotionError) as e:
        consolidate.promote_skill(config, agent, sid, sandbox_exit_code=0)
    assert missing.split("_")[0] in str(e.value)
    assert consolidate.active_skills(config, agent) == []


def test_a_failing_sandbox_run_prevents_activation(config, agent):
    """The skill regression test is the gate, not a formality."""
    sid = _skill_candidate(config, agent, skill_id="skl_regress")
    with pytest.raises(consolidate.SkillPromotionError) as e:
        consolidate.promote_skill(config, agent, sid, sandbox_exit_code=1)
    assert "sandbox tests failed" in str(e.value)
    assert consolidate.active_skills(config, agent) == []


def test_an_already_active_skill_is_not_promoted_twice(config, agent):
    sid = _skill_candidate(config, agent, skill_id="skl_once")
    consolidate.promote_skill(config, agent, sid, sandbox_exit_code=0)
    with pytest.raises(consolidate.SkillPromotionError):
        consolidate.promote_skill(config, agent, sid, sandbox_exit_code=0)


def test_promotion_is_an_event_and_rewrites_nothing(config, agent):
    """Append-only: the candidate row is still there after activation."""
    sid = _skill_candidate(config, agent, skill_id="skl_events")
    consolidate.promote_skill(config, agent, sid, sandbox_exit_code=0)
    rows = [s for s in ledger.read(config, "skills") if s.get("skill_id") == sid]
    assert [r["op"] for r in rows] == ["propose", "activate"]


# ── promotion is the only way a candidate becomes true ───────────────────────

def test_a_clean_candidate_can_be_promoted_by_the_owner(config, agent):
    _fail(config, agent, consolidate.MIN_SUPPORT_FOR_CANDIDATE)
    report = consolidate.run(config, agent)
    cand = report["semantic_candidates"][0]
    semantic.promote(config, agent, cand["memory_id"], by="owner")
    actives = [e["statement"] for e in semantic.active_entries(config, agent)]
    assert cand["statement"] in actives


def test_a_contradicted_candidate_cannot_be_promoted_silently(config, agent):
    semantic.record(config, agent, "the export always drains before it runs",
                    kind="invariant", scope=["global"], provenance=["owner"])
    _fail(config, agent, consolidate.MIN_SUPPORT_FOR_CANDIDATE,
          summary="the export never drains before it runs")
    report = consolidate.run(config, agent)
    cand = report["contradicted_candidates"][0]
    with pytest.raises(semantic.PromotionBlocked) as e:
        semantic.promote(config, agent, cand["memory_id"])
    assert "still" in str(e.value) and "active" in str(e.value)


def test_settling_the_disagreement_first_unblocks_it(config, agent):
    """The contradiction is resolved by a decision, not by asking twice."""
    prior = semantic.record(config, agent,
                            "the export always drains before it runs",
                            kind="invariant", scope=["global"],
                            provenance=["owner"])
    _fail(config, agent, consolidate.MIN_SUPPORT_FOR_CANDIDATE,
          summary="the export never drains before it runs")
    cand = consolidate.run(config, agent)["contradicted_candidates"][0]
    semantic.supersede(config, agent, prior["memory_id"],
                       "the export drains only when the queue is non-empty")
    semantic.promote(config, agent, cand["memory_id"],
                     resolves=[prior["memory_id"]])
    assert cand["statement"] in [e["statement"]
                                 for e in semantic.active_entries(config, agent)]


def test_promotion_never_rewrites_the_candidate_row(config, agent):
    _fail(config, agent, consolidate.MIN_SUPPORT_FOR_CANDIDATE)
    cand = consolidate.run(config, agent)["semantic_candidates"][0]
    semantic.promote(config, agent, cand["memory_id"])
    rows = [r for r in ledger.read(config, "semantic")
            if r.get("memory_id") == cand["memory_id"]]
    assert rows and all(r["status"] == "candidate" for r in rows)


def test_an_active_entry_is_not_promoted_again(config, agent):
    rec = semantic.record(config, agent, "the exporter writes CSV only",
                          kind="invariant", scope=["global"])
    with pytest.raises(semantic.PromotionBlocked):
        semantic.promote(config, agent, rec["memory_id"])
