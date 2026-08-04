"""One worker handing work to another — `work` → `funding`.

`work` produces the benchmark numbers; `funding` needs them for an application.
Dependencies already let the owner *order* those two. What was missing is the
worker that finishes something noticing the next step and saying so.

The whole design of it turns on one thing: **a worker may not give another
worker work.** An agent assigning to an agent with no owner in the loop is
"a worker that starts work on its own" wearing a second name, and both source
documents refuse that. So a handoff is a **proposal** — the same propose / hold
/ sign shape the house rules use, and for the same reason.

Four rules beyond that:

  * **you may only hand on what you finished.** A handoff from an unverified
    task is delegating unfinished business, and the receiving worker would be
    building on a claim rather than a result.
  * **the evidence travels as a link, not a summary.** The accepted task depends
    on the source task, so the next worker reads what was actually verified
    instead of what the previous one said about it.
  * **not to itself, and not to the manager.** One is just another task; the
    other drives nothing.
  * **the reason travels**, because the owner is deciding whether this is the
    next step, and "work suggested it" is not a reason.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             relay, task as tsk,
                                             verifier as vf, worker)


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
def work(config):
    return config.agents["work"]


@pytest.fixture
def funding(config):
    return config.agents["funding"]


def _task(config, agent, goal="produce the benchmark numbers"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    return tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                           pl.draft(d))


def _verified(config, agent, goal="produce the benchmark numbers"):
    return tsk.finish(config, agent, _task(config, agent, goal),
                      verdict=vf.parse("PASS: 1,204 rows produced"))


# ── proposing one ─────────────────────────────────────────────────────

def test_a_worker_can_hand_finished_work_on(config, work, funding):
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding",
                  goal="draft the application using these numbers",
                  because="the numbers are verified and the deadline is Friday")
    held = relay.pending(config, funding)
    assert held["from_agent"] == "work" and held["from_task"] == done.id


def test_the_proposal_carries_the_goal_and_the_reason(config, work, funding):
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding",
                  goal="draft the application using these numbers",
                  because="the numbers are verified")
    held = relay.pending(config, funding)
    assert held["goal"] == "draft the application using these numbers"
    assert "verified" in held["because"]


def test_a_proposal_with_no_reason_is_refused(config, work, funding):
    """The owner is deciding whether this is the next step. 'work suggested
    it' is not a reason."""
    done = _verified(config, work)
    with pytest.raises(ValueError):
        relay.propose(config, work, done, to="funding", goal="draft it",
                      because="   ")


# ── only what was finished ────────────────────────────────────────────

def test_unfinished_work_cannot_be_handed_on(config, work, funding):
    """The next worker would be building on a claim rather than a result."""
    held = _task(config, work)
    with pytest.raises(relay.NotFinished):
        relay.propose(config, work, held, to="funding", goal="draft it",
                      because="x")


def test_a_failed_task_cannot_be_handed_on(config, work, funding):
    t = _task(config, work)
    t.verdict = vf.parse("FAIL: the export is empty")
    tsk._touch(work, t, __import__("time").time)
    with pytest.raises(relay.NotFinished):
        relay.propose(config, work, t, to="funding", goal="draft it",
                      because="x")


# ── who may receive ───────────────────────────────────────────────────

def test_a_worker_cannot_hand_to_itself(config, work):
    done = _verified(config, work)
    with pytest.raises(ValueError, match="itself"):
        relay.propose(config, work, done, to="work", goal="more of the same",
                      because="x")


def test_a_worker_cannot_hand_to_the_manager(config, work):
    """It drives nothing. Handing it work is handing work to nobody."""
    done = _verified(config, work)
    with pytest.raises(relay.NotAWorker):
        relay.propose(config, work, done, to="sarsi-machine", goal="draft it",
                      because="x")


def test_an_unknown_recipient_is_refused(config, work):
    done = _verified(config, work)
    with pytest.raises(KeyError):
        relay.propose(config, work, done, to="ghost", goal="draft it",
                      because="x")


# ── it creates nothing until the owner accepts ────────────────────────

def test_proposing_creates_no_task(config, work, funding):
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding", goal="draft it",
                  because="x")
    assert tsk.all_of(config, funding) == []


def test_the_owner_accepting_creates_it(config, work, funding):
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding",
                  goal="draft the application", because="x")
    made = relay.accept(config, funding, by_owner=True)
    assert made.goal == "draft the application"
    assert [t.id for t in tsk.all_of(config, funding)] == [made.id]


def test_an_agent_cannot_accept_on_the_owners_behalf(config, work, funding):
    """An agent assigning to an agent is 'a worker that starts work on its
    own' wearing a second name."""
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding", goal="draft it",
                  because="x")
    with pytest.raises(relay.OwnerMustAccept):
        relay.accept(config, funding, by_owner=False)
    assert tsk.all_of(config, funding) == []


def test_the_owner_can_decline_it(config, work, funding):
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding", goal="draft it",
                  because="x")
    relay.decline(config, funding)
    assert relay.pending(config, funding) is None
    assert tsk.all_of(config, funding) == []


# ── the evidence travels as a link ────────────────────────────────────

def test_the_accepted_task_depends_on_the_source(config, work, funding):
    """So the next worker reads what was actually verified, rather than what
    the previous one said about it."""
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding", goal="draft it",
                  because="x")
    made = relay.accept(config, funding, by_owner=True)
    assert f"work/{done.id}" in made.depends_on


def test_the_accepted_task_starts_because_the_source_is_verified(config, work,
                                                                  funding):
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding", goal="draft it",
                  because="x")
    made = relay.accept(config, funding, by_owner=True)
    assert tsk.start(config, funding, made).state == tsk.RUNNING


# ── one at a time, and visible ────────────────────────────────────────

def test_only_one_handoff_is_held_per_worker(config, work, funding):
    a = _verified(config, work, "one")
    b = _verified(config, work, "two")
    relay.propose(config, work, a, to="funding", goal="first", because="x")
    relay.propose(config, work, b, to="funding", goal="second", because="y")
    assert relay.pending(config, funding)["goal"] == "second"


def test_attention_carries_a_pending_handoff(config, work, funding):
    from ai4science.harness.agents.sarsi import attention as att
    done = _verified(config, work)
    relay.propose(config, work, done, to="funding",
                  goal="draft the application", because="the numbers are in")

    class Blank:
        def capture(self, name):
            return ""

    got = att.needs(config, funding, pane=Blank(), live=lambda: set())
    kinds = [i.kind for i in got.items]
    assert "handoff" in kinds
    assert "work" in got.items[0].detail
