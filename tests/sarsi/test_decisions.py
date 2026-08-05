"""`decisions` — "what did you decide without me?"

The rung is recorded on every autonomous act and nothing reads it back, so the
one number that would show an agent over-reaching is invisible. That matters
more now that all seven run at **A2**, where the loop answers ordinary gates on
its own.

Four rules, and three of them are about what must *not* be counted:

  * **only the agent's own acts.** A gate the owner answered is not a decision
    the agent made; mixing them inflates the count until it means nothing.
  * **every entry carries the ceiling it was taken at.** Over-reach is a
    decision at a rung the agent should not have been at, and without the rung
    the list cannot show it.
  * **reading does not silently acknowledge.** An oversight tool whose second
    run shows nothing teaches the owner that nothing happened. Acknowledging is
    a separate, explicit act.
  * **the total is always stated**, so acknowledging can hide nothing — only
    move the line under it.
"""
import pytest

from ai4science.harness.agents.sarsi import (decisions as dec, ledger,
                                             plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             worker)


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


def _log(config, agent, state, *, task="tsk_1", ceiling="A2", evidence="…"):
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task, "state": state,
                   "ceiling": ceiling, "evidence": [evidence]})


# ── only the agent's own acts ─────────────────────────────────────────

def test_a_gate_the_agent_answered_is_a_decision(config, agent):
    _log(config, agent, "answered", evidence="the folder-trust prompt")
    got = dec.since(config, agent)
    assert [d.kind for d in got.items] == ["answered"]
    assert "folder-trust" in got.items[0].detail


def test_what_the_owner_did_is_not_a_decision_the_agent_made(config, agent):
    """Counting the owner's own guidance as the agent deciding would inflate
    the number until it stopped meaning anything."""
    _log(config, agent, "guided-by-owner", evidence="use the staging host")
    assert dec.since(config, agent).items == []


def test_an_observation_is_not_a_decision(config, agent):
    """'a gate is on screen' is something it SAW, not something it did."""
    for state in ("gate", "blocked", "question", "verified", "unverified",
                  "not-judged", "running", "planned"):
        _log(config, agent, state)
    assert dec.since(config, agent).items == []


def test_every_kind_of_autonomous_act_is_counted(config, agent):
    for state in ("answered", "submitted", "steered", "answered-question",
                  "retried"):
        _log(config, agent, state)
    assert len(dec.since(config, agent).items) == 5


def test_another_agents_decisions_are_not_this_ones(config, agent):
    _log(config, config.agents["social"], "answered")
    assert dec.since(config, agent).items == []


# ── the rung ──────────────────────────────────────────────────────────

def test_each_decision_names_the_ceiling_it_was_taken_at(config, agent):
    _log(config, agent, "answered", ceiling="A2")
    assert dec.since(config, agent).items[0].ceiling == "A2"


def test_a_decision_recorded_without_a_ceiling_says_unknown_not_a2(config, agent):
    """Guessing the rung is exactly the error this list exists to catch."""
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": "tsk_1", "state": "answered",
                   "evidence": ["x"]})
    assert dec.since(config, agent).items[0].ceiling == "unknown"


def test_the_summary_groups_by_rung(config, agent):
    _log(config, agent, "answered", ceiling="A2")
    _log(config, agent, "submitted", ceiling="A1")
    summary = dec.since(config, agent).summary
    assert "A2" in summary and "A1" in summary


def test_the_operator_records_the_ceiling_it_acted_at(config, agent):
    """The ledger held the act and not the rung, which is the whole gap."""
    from ai4science.harness.agents.sarsi import operator as op

    d = worker.Directive(agent_id=agent.id, goal="finish it")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t.session = {"name": "work-0001", "pid": 1, "cwd": "/tmp", "ceiling": "A2"}
    t.state = tsk.RUNNING
    tsk._touch(agent, t, __import__("time").time)

    class Pane:
        def capture(self, name):
            return (" Is this a project you created or one you trust\n"
                    " ❯ 1. Yes\n   2. No\n")

        def send(self, name, text):
            pass

        def key(self, name, key):
            pass

    op.tick(config, agent, t, pane=Pane())
    assert dec.since(config, agent).items[0].ceiling == "A2"


# ── acknowledging is explicit ─────────────────────────────────────────

def test_reading_twice_shows_the_same_thing(config, agent):
    """A tool whose second run shows nothing teaches the owner that nothing
    happened."""
    _log(config, agent, "answered")
    assert len(dec.since(config, agent).items) == 1
    assert len(dec.since(config, agent).items) == 1


def test_acknowledging_moves_the_line(config, agent):
    _log(config, agent, "answered")
    dec.acknowledge(config, agent)
    assert dec.since(config, agent).items == []


def test_a_decision_after_the_acknowledgement_still_shows(config, agent):
    _log(config, agent, "answered")
    dec.acknowledge(config, agent)
    _log(config, agent, "submitted")
    assert [d.kind for d in dec.since(config, agent).items] == ["submitted"]


def test_the_total_is_stated_even_when_none_are_new(config, agent):
    """Acknowledging must be able to move the line and never hide history."""
    _log(config, agent, "answered")
    dec.acknowledge(config, agent)
    got = dec.since(config, agent)
    assert got.items == [] and got.total == 1
    assert "1" in got.summary


def test_everything_can_still_be_read(config, agent):
    _log(config, agent, "answered")
    dec.acknowledge(config, agent)
    assert len(dec.all_of(config, agent).items) == 1


# ── across the fleet ──────────────────────────────────────────────────

def test_the_fleet_view_names_which_agent_decided(config):
    _log(config, config.agents["sarsi-worker"], "answered")
    _log(config, config.agents["abraham"], "submitted")
    rows = dec.across(config)
    assert {d.agent_id for d in rows.items} == {"sarsi-worker", "abraham"}


def test_a_decision_in_the_same_second_as_the_acknowledgement_still_shows(
        config, agent):
    """The ledger stamps to the second. Comparing timestamps would swallow a
    decision taken in that same second — silently, and exactly at the moment
    the owner had just looked away."""
    _log(config, agent, "answered")
    dec.acknowledge(config, agent)
    _log(config, agent, "submitted")          # same second, in practice
    assert [d.kind for d in dec.since(config, agent).items] == ["submitted"]
