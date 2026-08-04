"""A budget per task — so a session that loops stops instead of running all night.

One task burned about eight minutes of unattended waiting and nothing noticed.
A session that has lost the thread does not announce it; it keeps working, and
the only thing that ends it is somebody looking.

Four rules, and the first two are about what a budget must *not* do:

  * **it pauses, it does not fail.** Running out of budget says nothing about
    whether the work was right. The plan, the verdict and the history survive,
    and raising the budget resumes it.
  * **unknown is not over.** Steps are counted from the session transcript; if
    that cannot be read, the step budget is not enforced — stopping real work on
    the strength of a number nobody could read is worse than the overrun. Time
    is always measurable, so the clock still bites.
  * **there is no default budget.** A default either kills legitimate long work
    or is so loose it never fires; both teach the owner to ignore it. It is
    declared, per task, or it does not exist.
  * **it is checked before the loop acts**, not after — a budget enforced after
    the next step has already run is one step too late, every time.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (budget as bg, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"),
                  root=tmp_path / "state")
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["work"]


class FakeRuntime:
    engine = "claude"

    def __init__(self):
        self.sent, self.stopped = [], []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def stop(self, name):
        self.stopped.append(name)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _task(config, agent, *, steps=None, minutes=None):
    plan = pl.Plan(goal="finish the export", max_steps=steps,
                   max_minutes=minutes,
                   phases=[pl.Phase(title="x", verified_when="y")])
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), plan)
    return tsk.start(config, agent, t)


def _running(config, agent, rt, **kw):
    return ses.assign(config, agent, _task(config, agent, **kw), runtime=rt)


def _acts(n):
    return lambda cwd: [{"name": "Bash", "input": {}} for _ in range(n)]


# ── declared, never assumed ───────────────────────────────────────────

def test_a_plan_can_declare_a_budget(tmp_path):
    text = """\
# finish the export

Budget: 40 steps, 30 minutes

## Phase 1 — do it
Verified when: it is done

## Permissions needed
- none
"""
    parsed = pl.parse(text)
    assert parsed.max_steps == 40 and parsed.max_minutes == 30


def test_the_budget_survives_a_render_and_reparse():
    original = pl.Plan(goal="g", max_steps=40, max_minutes=30,
                       phases=[pl.Phase(title="x", verified_when="y")])
    again = pl.parse(original.render())
    assert (again.max_steps, again.max_minutes) == (40, 30)


def test_a_task_with_no_declaration_has_no_budget(config, agent):
    """A default either kills legitimate long work or never fires."""
    t = _task(config, agent)
    assert bg.check(config, agent, t, acts=_acts(10_000)).over is False


# ── the step budget ───────────────────────────────────────────────────

def test_under_the_step_budget_is_not_over(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=40)
    assert bg.check(config, agent, t, acts=_acts(10)).over is False


def test_over_the_step_budget_is_over(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=40)
    got = bg.check(config, agent, t, acts=_acts(41))
    assert got.over is True and "step" in got.why.lower()


def test_the_reason_says_how_far_over(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=40)
    assert "41" in bg.check(config, agent, t, acts=_acts(41)).why


def test_an_unreadable_transcript_does_not_count_as_over(config, agent):
    """Stopping real work on a number nobody could read is worse than the
    overrun it was meant to prevent."""
    def broken(cwd):
        raise OSError("no transcript")

    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=1)
    got = bg.check(config, agent, t, acts=broken)
    assert got.over is False
    assert got.steps_known is False


# ── the clock ─────────────────────────────────────────────────────────

def test_under_the_time_budget_is_not_over(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, minutes=30)
    t.session["started_at"] = time.time() - 60
    tsk._touch(agent, t, time.time)
    assert bg.check(config, agent, tsk.get(config, agent, t.id),
                    acts=_acts(1)).over is False


def test_over_the_time_budget_is_over(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, minutes=30)
    t.session["started_at"] = time.time() - 3600
    tsk._touch(agent, t, time.time)
    got = bg.check(config, agent, tsk.get(config, agent, t.id), acts=_acts(1))
    assert got.over is True and "minute" in got.why.lower()


def test_the_clock_bites_even_when_steps_cannot_be_read(config, agent):
    """Time is always measurable from the session's own start stamp."""
    def broken(cwd):
        raise OSError("no transcript")

    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=40, minutes=30)
    t.session["started_at"] = time.time() - 3600
    tsk._touch(agent, t, time.time)
    assert bg.check(config, agent, tsk.get(config, agent, t.id),
                    acts=broken).over is True


def test_a_session_with_no_start_stamp_has_no_clock(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, minutes=1)
    t.session.pop("started_at", None)
    tsk._touch(agent, t, time.time)
    got = bg.check(config, agent, tsk.get(config, agent, t.id), acts=_acts(1))
    assert got.over is False and got.minutes_known is False


# ── running out pauses, it does not fail ──────────────────────────────

def test_going_over_stops_the_task_and_keeps_the_plan(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=1)
    t = bg.enforce(config, agent, t, acts=_acts(5), runtime=rt)
    after = tsk.get(config, agent, t.id)
    assert after.state == tsk.OFF
    assert tsk.read_plan(config, agent, after) is not None


def test_going_over_is_not_a_verdict(config, agent):
    """Running out of budget says nothing about whether the work was right."""
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=1)
    t = bg.enforce(config, agent, t, acts=_acts(5), runtime=rt)
    assert tsk.get(config, agent, t.id).verdict is None


def test_going_over_closes_the_session(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=1)
    name = t.session["name"]
    bg.enforce(config, agent, t, acts=_acts(5), runtime=rt)
    assert rt.stopped == [name]


def test_staying_within_changes_nothing(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=40)
    before = tsk.get(config, agent, t.id).state
    bg.enforce(config, agent, t, acts=_acts(5), runtime=rt)
    assert tsk.get(config, agent, t.id).state == before
    assert rt.stopped == []


def test_it_is_recorded_so_the_owner_can_see_why_it_stopped(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=1)
    bg.enforce(config, agent, t, acts=_acts(5), runtime=rt)
    states = [e.get("state") for e in ledger.read(config, "reports")]
    assert "over-budget" in states


# ── the loop checks BEFORE it acts ────────────────────────────────────

def test_the_supervision_loop_stops_before_taking_another_step(config, agent):
    """A budget enforced after the next step has run is one step too late,
    every time."""
    from ai4science.harness.agents.sarsi import operator as op

    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=1)
    t.plan_agreed = True
    t.kickoff_pending = None
    tsk._touch(agent, t, time.time)

    class Pane:
        def __init__(self):
            self.sent = []

        def capture(self, name):
            return " Claude wants to run: ls\n ❯ 1. Yes\n   2. No\n"

        def send(self, name, text):
            self.sent.append(text)

        def key(self, name, key):
            pass

    pane = Pane()
    action = op.tick(config, agent, t, pane=pane, acts=_acts(5))
    assert action.kind == "over-budget"
    assert pane.sent == []


# ── and the owner is told ─────────────────────────────────────────────

def test_attention_carries_a_task_that_ran_out(config, agent):
    from ai4science.harness.agents.sarsi import attention as att
    rt = FakeRuntime()
    t = _running(config, agent, rt, steps=1)
    bg.enforce(config, agent, t, acts=_acts(5), runtime=rt)

    class Blank:
        def capture(self, name):
            return ""

    kinds = [i.kind for i in att.needs(config, agent, pane=Blank()).items]
    assert "over-budget" in kinds
