"""Planning spends its own budget, not the work's.

Live on `work`, twice. A task declared `--steps 24`, the planning session used
25 of them reading the folder and drafting a plan, and the loop stopped it:

    over-budget — 25 steps is past the 24 this plan declared

Correct against the number, and useless: `~/live-d2` was empty, the work had not
begun, and the budget the owner set for *doing the job* was gone before the job
started. A ceiling that a task can exhaust without attempting its goal does not
bound the work, it just makes the failure arrive earlier and less informatively.

So the two are counted apart:

  * **the declared budget is the WORK budget.** It is what the owner is thinking
    about when they write `--steps 24`, and it now begins when the work does.
  * **planning has its own, declared separately** — and, like every budget here,
    **no default**: an undeclared planning ceiling is not enforced, because a
    default either kills legitimate long planning or never fires.
  * **the boundary is `release`**, the call that raises the ceiling from A0 and
    means "stop planning, start working". It records how much was spent by
    then, and the work count is measured from there.
  * **unknown is still not over.** A task that reached work without that mark
    has no baseline, and counting from zero would charge the work for planning
    all over again — so it says the count is unknown rather than guessing.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (budget as bdg, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, worker)


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


class FakeRuntime:
    engine = "claude"

    def __init__(self):
        self.sent = []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None,
              writable=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _task(config, agent, *, steps=None, minutes=None, plan_steps=None,
          plan_minutes=None):
    d = worker.Directive(agent_id=agent.id, goal="write the note")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t.max_steps, t.max_minutes = steps, minutes
    t.max_plan_steps, t.max_plan_minutes = plan_steps, plan_minutes
    t.session = {"name": "work-abcd", "cwd": str(tsk.dir_of(agent, t.id)),
                 "started_at": time.time()}
    return tsk._touch(agent, t, time.time)


def _acts(n):
    return lambda cwd: [{"name": "Read", "input": {}} for _ in range(n)]


# ── planning does not spend the work budget ───────────────────────────

def test_planning_steps_do_not_count_against_the_work_budget(config, agent):
    """The live failure: 25 steps of planning against a 24-step WORK budget."""
    t = _task(config, agent, steps=24)
    t.plan_agreed = False
    assert bdg.check(config, agent, t, acts=_acts(25)).over is False


def test_the_work_budget_starts_where_planning_ended(config, agent):
    """25 spent planning, then 3 of work — that is 3 against the 24."""
    t = _task(config, agent, steps=24)
    t.steps_before_work = 25
    t.plan_agreed = True
    status = bdg.check(config, agent, t, acts=_acts(28))
    assert status.over is False and status.steps == 3


def test_and_it_still_bites_when_the_work_runs_long(config, agent):
    t = _task(config, agent, steps=24)
    t.steps_before_work = 25
    t.plan_agreed = True
    status = bdg.check(config, agent, t, acts=_acts(25 + 25))
    assert status.over is True and "25" in status.why


# ── planning's own ceiling ────────────────────────────────────────────

def test_a_declared_planning_budget_is_enforced(config, agent):
    t = _task(config, agent, steps=24, plan_steps=10)
    t.plan_agreed = False
    status = bdg.check(config, agent, t, acts=_acts(11))
    assert status.over is True
    assert "planning" in status.why.lower()


def test_under_it_planning_runs_on(config, agent):
    t = _task(config, agent, steps=24, plan_steps=10)
    t.plan_agreed = False
    assert bdg.check(config, agent, t, acts=_acts(9)).over is False


def test_no_planning_budget_declared_is_not_enforced(config, agent):
    """Every budget here is declared or absent; a default either kills
    legitimate long planning or never fires."""
    t = _task(config, agent, steps=24)
    t.plan_agreed = False
    assert bdg.check(config, agent, t, acts=_acts(500)).over is False


def test_the_planning_clock_is_its_own_too(config, agent):
    t = _task(config, agent, minutes=20, plan_minutes=5)
    t.plan_agreed = False
    t.session["started_at"] = time.time() - 6 * 60
    status = bdg.check(config, agent, t, acts=_acts(0))
    assert status.over is True and "planning" in status.why.lower()


def test_and_the_work_clock_does_not_fire_during_planning(config, agent):
    """20 minutes of planning must not spend the work's 20."""
    t = _task(config, agent, minutes=20)
    t.plan_agreed = False
    t.session["started_at"] = time.time() - 25 * 60
    assert bdg.check(config, agent, t, acts=_acts(0)).over is False


# ── the boundary is `release` ─────────────────────────────────────────

def test_release_records_what_planning_spent(config, agent):
    """`release` is the call that means "stop planning, start working"."""
    t = _task(config, agent, steps=24)
    t.plan_agreed = True
    out = ses.release(config, agent, t, runtime=FakeRuntime(),
                      acts=_acts(7))
    assert out.steps_before_work == 7


def test_it_also_starts_the_work_clock(config, agent):
    t = _task(config, agent, minutes=20)
    t.plan_agreed = True
    t.session["started_at"] = time.time() - 30 * 60
    out = ses.release(config, agent, t, runtime=FakeRuntime(), acts=_acts(0))
    # the work has just begun, whatever planning took
    assert bdg.check(config, agent, out, acts=_acts(0)).over is False


def test_with_no_mark_it_counts_from_zero_rather_than_not_at_all(config, agent):
    """The first version of this said "unknown, so not enforced" — and the
    regression showed what that costs: the mark is made where planning ends,
    `release` is an OWNER command the supervision loop never calls, and most
    tasks therefore have no mark at all. Treating that as unknown switched the
    step budget off for nearly every task.

    So no mark means the floor is zero: the old behaviour, which can only stop a
    task EARLIER than the truth. A budget that bites too soon is a nuisance; one
    that quietly stopped applying is the failure it was written to prevent.
    """
    t = _task(config, agent, steps=24)
    t.plan_agreed = True
    t.steps_before_work = None
    status = bdg.check(config, agent, t, acts=_acts(100))
    assert status.over is True and status.steps == 100


def test_the_mark_is_made_when_the_session_plan_is_adopted(config, agent):
    """Not only at `release`. That is the owner's command; this is the one the
    loop actually reaches on the automatic path."""
    from ai4science.harness.agents.sarsi import plan as _pl
    t = _task(config, agent, steps=24)
    t.plan_agreed = False
    t.steps_before_work = None
    out = tsk.adopt_plan(config, agent, t,
                         _pl.Plan(goal="g", phases=[_pl.Phase(
                             title="x", verified_when="y")]))
    assert out.plan_agreed is True
    assert out.work_started_at is not None


# ── declaring it ──────────────────────────────────────────────────────

def test_the_plan_carries_the_planning_budget(config, agent):
    """It travels in the plan like the work budget does — which is by
    `dataclasses.replace` on the draft, not on the directive — so `sarsi plan`
    shows the owner BOTH ceilings rather than one and a surprise."""
    from dataclasses import replace
    d = worker.Directive(agent_id=agent.id, goal="g")
    text = replace(pl.draft(d), max_steps=24, max_plan_steps=10,
                   max_plan_minutes=5).render()
    parsed = pl.parse(text)
    assert parsed.max_plan_steps == 10 and parsed.max_plan_minutes == 5
    assert parsed.max_steps == 24, "the work budget is still its own line"


def test_the_two_budget_lines_do_not_read_as_each_other(config, agent):
    """`Planning budget:` ends in the word the other line starts with, so the
    order they are matched in decides whether one silently becomes the other."""
    from dataclasses import replace
    d = worker.Directive(agent_id=agent.id, goal="g")
    text = replace(pl.draft(d), max_plan_steps=10).render()
    assert pl.parse(text).max_steps is None
