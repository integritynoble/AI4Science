"""The playbook, and the governed loop that changes it.

Recursive self-improvement here is one shape: **propose → evidence-based
rationale → owner signs → adopt.** Never a silent change, and never a
self-promotion.

The refusals matter more than the promotions:
  * an agent cannot promote its own candidate;
  * it cannot raise its own ceiling, or widen any authority, at any version;
  * a signature with no pending candidate does nothing.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import playbook as pb, registry as reg


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
    return config.agents["work"]


# ── the playbook itself ───────────────────────────────────────────────

def test_a_fresh_agent_starts_at_v1_with_defaults(config, agent):
    book = pb.read(config, agent)
    assert book["version"] == 1
    assert book["params"]["max_concurrent_tasks"] == agent.max_concurrent_tasks


def test_each_agent_has_its_own(config):
    pb.write(config, config.agents["work"], {"max_concurrent_tasks": 9}, version=2)
    assert pb.read(config, config.agents["abraham"])["version"] == 1


def test_the_playbook_is_on_disk_where_the_owner_can_read_it(config, agent):
    pb.read(config, agent)
    assert (agent.playbook).exists()
    assert json.loads(agent.playbook.read_text())["version"] == 1


# ── propose ───────────────────────────────────────────────────────────

def test_a_proposal_cites_real_numbers(config, agent):
    evidence = {"tasks_held": 7, "blocked_by_concurrency": 4,
                "verified": 3, "refused": 0}
    candidate = pb.propose(config, agent, evidence=evidence)
    assert candidate.change is not None
    assert "4" in candidate.rationale          # the number it acted on


def test_with_nothing_to_justify_a_change_it_says_so_honestly(config, agent):
    evidence = {"tasks_held": 1, "blocked_by_concurrency": 0,
                "verified": 1, "refused": 0}
    candidate = pb.propose(config, agent, evidence=evidence)
    assert candidate.change is None
    assert "no change" in candidate.rationale.lower()


def test_a_proposal_is_held_not_applied(config, agent):
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 4})
    assert pb.read(config, agent)["version"] == 1        # unchanged until signed


# ── sign ──────────────────────────────────────────────────────────────

def test_the_owner_signing_promotes_and_bumps_the_version(config, agent):
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 4})
    out = pb.sign(config, agent, by_owner=True)
    assert out.adopted is True
    assert pb.read(config, agent)["version"] == 2


def test_the_promoted_parameter_is_live_on_disk(config, agent):
    before = pb.read(config, agent)["params"]["max_concurrent_tasks"]
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 4})
    pb.sign(config, agent, by_owner=True)
    after = json.loads(agent.playbook.read_text())["params"]["max_concurrent_tasks"]
    assert after > before


def test_an_agent_cannot_promote_its_own_candidate(config, agent):
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 4})
    with pytest.raises(pb.OwnerMustSign):
        pb.sign(config, agent, by_owner=False)
    assert pb.read(config, agent)["version"] == 1


def test_a_signature_with_no_candidate_does_nothing(config, agent):
    out = pb.sign(config, agent, by_owner=True)
    assert out.adopted is False
    assert pb.read(config, agent)["version"] == 1


def test_declining_discards_the_candidate(config, agent):
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 4})
    pb.discard(config, agent)
    out = pb.sign(config, agent, by_owner=True)
    assert out.adopted is False and pb.read(config, agent)["version"] == 1


def test_signing_a_no_change_candidate_changes_nothing(config, agent):
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 0})
    out = pb.sign(config, agent, by_owner=True)
    assert out.adopted is False
    assert pb.read(config, agent)["version"] == 1


# ── what RSI may never touch ──────────────────────────────────────────

def test_a_candidate_may_not_change_the_ceiling(config, agent):
    """Agents can never raise their own ceiling — not even by proposing it and
    being signed. Authority is not a tunable parameter."""
    with pytest.raises(pb.NotTunable, match="ceiling"):
        pb.propose(config, agent, evidence={}, change={"ceiling": "A3"})


def test_a_candidate_may_not_grant_standing_authority(config, agent):
    with pytest.raises(pb.NotTunable):
        pb.propose(config, agent, evidence={}, change={"standing_grants": True})


def test_a_candidate_may_not_invent_a_parameter(config, agent):
    """A parameter nothing reads is a number that looks like a policy."""
    with pytest.raises(pb.NotTunable, match="unknown"):
        pb.propose(config, agent, evidence={}, change={"cleverness": 11})


def test_every_tunable_is_actually_consumed_somewhere(config, agent):
    """A playbook full of parameters nothing reads is theatre."""
    for name in pb.TUNABLE:
        assert name in pb.CONSUMED_BY


def test_a_promoted_parameter_really_changes_what_the_agent_does(config, agent):
    """The claim in CONSUMED_BY has to be true, or the whole loop is a number
    that moves on disk and nowhere else."""
    from ai4science.harness.agents.sarsi import plan as pl, task as tsk, worker

    def new_task(goal):
        d = worker.Directive(agent_id=agent.id, goal=goal)
        p = pl.Plan(goal=goal, phases=[pl.Phase(title="x", verified_when="y")])
        return tsk.attach_plan(config, agent, tsk.create(config, agent, d), p)

    pb.write(config, agent, {"max_concurrent_tasks": 1})
    first = tsk.start(config, agent, new_task("one"))
    second = tsk.start(config, agent, new_task("two"))
    assert first.state == tsk.RUNNING
    assert second.blocked_by == "concurrency"       # the playbook value bit

    pb.write(config, agent, {"max_concurrent_tasks": 2})
    assert tsk.start(config, agent, second).state == tsk.RUNNING
