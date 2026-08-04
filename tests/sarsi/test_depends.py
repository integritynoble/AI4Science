"""One task waiting on another — `funding` needs `work`'s numbers.

Without this the owner is the scheduler: they hold the ordering in their head
and start the second task when they remember the first one finished. The
motivating case crosses agents, so a dependency names `<agent>/<task>`, not just
a task id.

What "finished" means here is the strict thing: **verified**. Not stopped, not
archived, not "the session said it was done". Archiving is how a task is
*closed*, which is not the same as succeeded — treating it as satisfaction would
let a task that was abandoned release everything queued behind it.

Two refusals, both at declaration time, because a task that can never run must
say so while someone is still looking at it:

  * **a dependency on a task that does not exist** is refused. Otherwise it
    waits forever on nothing, and waiting forever looks exactly like patience.
  * **a cycle** is refused. Two tasks each waiting on the other never run, and
    silently never running is the worst outcome this board can produce.

And it never auto-starts what it unblocks. `run` is the owner's opt-in, and that
is the only line between "I asked a question" and "I authorised work".
"""
import pytest

from ai4science.harness.agents.sarsi import (depends as dep, plan as pl,
                                             registry as reg, task as tsk,
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


def _task(config, agent, goal="a job", *, after=()):
    plan = pl.Plan(goal=goal, depends_on=list(after),
                   phases=[pl.Phase(title="x", verified_when="y")])
    d = worker.Directive(agent_id=agent.id, goal=goal)
    return tsk.attach_plan(config, agent, tsk.create(config, agent, d), plan)


def _verify(config, agent, t):
    return tsk.finish(config, agent, t, verdict=vf.parse("PASS: done"))


# ── declaring it ──────────────────────────────────────────────────────

def test_a_plan_can_declare_what_it_waits_on(tmp_path):
    text = """\
# draft the application

Depends on: work/tsk_abc123

## Phase 1 — do it
Verified when: it is done

## Permissions needed
- none
"""
    assert list(pl.parse(text).depends_on) == ["work/tsk_abc123"]


def test_the_declaration_survives_a_render_and_reparse():
    original = pl.Plan(goal="g", depends_on=["work/tsk_a", "work/tsk_b"],
                       phases=[pl.Phase(title="x", verified_when="y")])
    assert list(pl.parse(original.render()).depends_on) == ["work/tsk_a",
                                                            "work/tsk_b"]


# ── it holds the task back ────────────────────────────────────────────

def test_a_task_waiting_on_an_unverified_one_does_not_start(config, work, funding):
    first = _task(config, work, "produce the numbers")
    second = _task(config, funding, "use the numbers",
                   after=[f"work/{first.id}"])
    started = tsk.start(config, funding, second)
    assert started.state != tsk.RUNNING
    assert first.id in (started.blocked_by or "")


def test_it_starts_once_the_dependency_is_verified(config, work, funding):
    first = _task(config, work, "produce the numbers")
    _verify(config, work, first)
    second = _task(config, funding, "use the numbers",
                   after=[f"work/{first.id}"])
    assert tsk.start(config, funding, second).state == tsk.RUNNING


def test_every_dependency_must_be_verified(config, work, funding):
    a = _task(config, work, "one")
    b = _task(config, work, "two")
    _verify(config, work, a)
    third = _task(config, funding, "three",
                  after=[f"work/{a.id}", f"work/{b.id}"])
    started = tsk.start(config, funding, third)
    assert started.state != tsk.RUNNING and b.id in (started.blocked_by or "")


def test_a_dependency_in_the_same_agent_can_be_named_bare(config, work):
    first = _task(config, work, "one")
    second = _task(config, work, "two", after=[first.id])
    assert tsk.start(config, work, second).state != tsk.RUNNING


# ── closed is not succeeded ───────────────────────────────────────────

def test_an_archived_dependency_does_not_satisfy_it(config, work, funding):
    """Archiving is how a task is CLOSED. A task that was abandoned must not
    release everything queued behind it."""
    first = _task(config, work, "produce the numbers")
    tsk.archive(config, work, first)
    second = _task(config, funding, "use them", after=[f"work/{first.id}"])
    assert tsk.start(config, funding, second).state != tsk.RUNNING


def test_a_stopped_dependency_does_not_satisfy_it(config, work, funding):
    first = _task(config, work, "produce the numbers")
    tsk.turn_off(config, work, first)
    second = _task(config, funding, "use them", after=[f"work/{first.id}"])
    assert tsk.start(config, funding, second).state != tsk.RUNNING


def test_an_archived_but_verified_dependency_does_satisfy_it(config, work, funding):
    """It was verified before it was filed away. Closing the record does not
    unmake the verdict."""
    first = _verify(config, work, _task(config, work, "produce the numbers"))
    tsk.archive(config, work, first)
    second = _task(config, funding, "use them", after=[f"work/{first.id}"])
    assert tsk.start(config, funding, second).state == tsk.RUNNING


# ── the refusals, at declaration time ─────────────────────────────────

def test_a_dependency_on_a_task_that_does_not_exist_is_refused(config, funding):
    """Waiting forever on nothing looks exactly like patience."""
    with pytest.raises(dep.Unknown, match="tsk_nothing"):
        dep.check(config, funding, ["work/tsk_nothing"])


def test_a_dependency_on_an_unknown_agent_is_refused(config, funding):
    with pytest.raises(dep.Unknown, match="ghost"):
        dep.check(config, funding, ["ghost/tsk_abc"])


def test_a_task_cannot_wait_on_itself(config, work):
    first = _task(config, work, "one")
    with pytest.raises(dep.Cycle):
        dep.check(config, work, [f"work/{first.id}"], task_id=first.id)


def test_a_cycle_is_refused(config, work):
    """Two tasks each waiting on the other never run, and silently never
    running is the worst outcome this board can produce."""
    a = _task(config, work, "one")
    b = _task(config, work, "two", after=[f"work/{a.id}"])
    with pytest.raises(dep.Cycle):
        dep.check(config, work, [f"work/{b.id}"], task_id=a.id)


def test_a_longer_cycle_is_refused_too(config, work):
    a = _task(config, work, "one")
    b = _task(config, work, "two", after=[f"work/{a.id}"])
    c = _task(config, work, "three", after=[f"work/{b.id}"])
    with pytest.raises(dep.Cycle):
        dep.check(config, work, [f"work/{c.id}"], task_id=a.id)


# ── it does not start anything by itself ──────────────────────────────

def test_unblocking_does_not_start_the_waiting_task(config, work, funding):
    """`run` is the owner's opt-in, and it is the only line between 'I asked a
    question' and 'I authorised work'."""
    first = _task(config, work, "produce the numbers")
    second = _task(config, funding, "use them", after=[f"work/{first.id}"])
    tsk.start(config, funding, second)
    _verify(config, work, first)
    assert tsk.get(config, funding, second.id).state != tsk.RUNNING


# ── the owner can see what is waiting ─────────────────────────────────

def test_the_board_says_which_task_it_waits_on(config, work, funding):
    first = _task(config, work, "produce the numbers")
    second = _task(config, funding, "use them", after=[f"work/{first.id}"])
    tsk.start(config, funding, second)
    from ai4science.harness.agents.sarsi import chat
    out = chat.handle(config, funding, "/tasks", surface="cli")
    assert first.id in out


def test_what_is_ready_to_start_can_be_listed(config, work, funding):
    first = _task(config, work, "produce the numbers")
    blocked = _task(config, funding, "use them", after=[f"work/{first.id}"])
    assert dep.blocked(config, funding) == [blocked.id]
    _verify(config, work, first)
    assert dep.blocked(config, funding) == []
