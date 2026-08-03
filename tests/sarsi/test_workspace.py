"""The workspace a node is given — the history it plans and steers from.

A node with no workspace starts every time from nothing, which is how an agent
re-learns the same thing weekly and asks for a permission it was already told
about. The workspace is where `W_name` earns its keep.

It is **built from records, never summarised by a model.** A model-written
précis of what happened is `L7` narration standing in for history: it reads like
evidence and is not. So every line here is promoted from something already
written down — the owner log, the grants, the ledgers, the plans.

Three rules it keeps:

  * **bounded, with the overflow counted** rather than silently truncated. "and
    14 more" is information; a quiet cut is a lie about completeness.
  * **no secret ever appears.** The vault ledger records which secret was asked
    for; that name may travel, its value never does.
  * **no host-local fact travels.** Tools, paths and resources are about *this*
    machine and mean nothing off it — copying them upward is how a fleet
    convinces itself it can do something it cannot.
"""
import pytest

from ai4science.harness.agents.sarsi import (ledger, ownerlog, plan as pl,
                                             registry as reg, task as tsk,
                                             workspace as ws, worker)


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


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    return tsk.create(config, agent, d)


# ── what it carries ───────────────────────────────────────────────────

def test_it_carries_what_the_owner_said(config, agent):
    ownerlog.append(config, agent, "always use the staging host", surface="cli")
    text = ws.render(config, agent, _task(config, agent))
    assert "staging host" in text


def test_it_carries_the_grants_already_held(config, agent):
    t = _task(config, agent)
    t = tsk.grant(config, agent, t, "write /home/me/reports")
    assert "/home/me/reports" in ws.render(config, agent, t)


def test_it_carries_criteria_that_earned_a_pass_before(config, agent):
    """Precedent: a criterion that was accepted once is a good shape to reuse."""
    done = tsk.attach_plan(config, agent, _task(config, agent, "an earlier job"),
                           pl.Plan(goal="an earlier job",
                                   phases=[pl.Phase(title="x",
                                                    verified_when="rows.csv has 1,204 lines")]))
    tsk.finish(config, agent, tsk.start(config, agent, done),
               verdict={"state": "PASS", "by": "verifier"})
    assert "1,204 lines" in ws.render(config, agent, _task(config, agent))


def test_it_carries_a_planning_miss(config, agent):
    """A permission discovered mid-run is exactly what the NEXT plan should
    declare up front."""
    ledger.append(config, "reports",
                  {"agent": "work", "task": "tsk_old", "state": "gate",
                   "evidence": ["a gate this loop does not recognise: write /etc"]})
    assert "write /etc" in ws.render(config, agent, _task(config, agent))


def test_a_fresh_agent_has_an_honest_empty_workspace(config, agent):
    text = ws.render(config, agent, _task(config, agent))
    assert "nothing" in text.lower() or text.strip() == ""


# ── what it must never carry ──────────────────────────────────────────

def test_no_secret_value_ever_appears(config, agent):
    from ai4science.harness.agents.sarsi import vault
    vault.put(config, "mail.read", "hunter2")
    vault.ask(config, agent_id="work", secret="mail.read", act="read",
              purpose="p", prompt=lambda **kw: "yes")
    text = ws.render(config, agent, _task(config, agent))
    assert "hunter2" not in text


def test_a_secret_may_be_named_though(config, agent):
    """`VLT` has to be able to say which one, or the owner cannot grant it."""
    from ai4science.harness.agents.sarsi import vault
    vault.put(config, "mail.read", "hunter2")
    vault.ask(config, agent_id="work", secret="mail.read", act="read",
              purpose="p", prompt=lambda **kw: "no")
    assert "mail.read" in ws.render(config, agent, _task(config, agent))


def test_no_host_local_fact_travels(config, agent):
    (agent.host / "tools.json").write_text('{"matlab": {"how": "/opt/matlab/bin"}}')
    assert "/opt/matlab" not in ws.render(config, agent, _task(config, agent))


def test_another_agents_history_never_appears(config):
    ownerlog.append(config, config.agents["abraham"], "book the dentist",
                    surface="cli")
    text = ws.render(config, config.agents["work"],
                     _task(config, config.agents["work"]))
    assert "dentist" not in text


# ── bounded, and honest about it ──────────────────────────────────────

def test_it_is_bounded(config, agent):
    for i in range(60):
        ownerlog.append(config, agent, f"thing number {i}", surface="cli")
    text = ws.render(config, agent, _task(config, agent))
    assert len(text) < 8000


def test_the_overflow_is_counted_not_silently_dropped(config, agent):
    for i in range(60):
        ownerlog.append(config, agent, f"thing number {i}", surface="cli")
    text = ws.render(config, agent, _task(config, agent))
    assert "more" in text.lower()


def test_it_is_promoted_from_records_not_summarised(config, agent):
    """A model-written précis would read like evidence and not be it. The exact
    words the owner used survive."""
    ownerlog.append(config, agent, "never touch production", surface="telegram")
    assert "never touch production" in ws.render(config, agent, _task(config, agent))


# ── the planning node gets it ─────────────────────────────────────────

def test_the_planning_kickoff_carries_the_workspace(config, agent):
    from ai4science.harness.agents.sarsi import session as ses
    ownerlog.append(config, agent, "always use the staging host", surface="cli")
    t = _task(config, agent)
    assert "staging host" in ses.planning_kickoff(config, agent, t)


def test_the_planning_kickoff_still_carries_the_goal(config, agent):
    from ai4science.harness.agents.sarsi import session as ses
    t = _task(config, agent)
    assert "finish the export" in ses.planning_kickoff(config, agent, t)
