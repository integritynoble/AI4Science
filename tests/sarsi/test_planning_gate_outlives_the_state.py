"""The session is still planning after the record says it stopped.

A live run, captured in full:

    planned — 3 criterion(s); …
    busy
    abstained — an option menu this loop has no rule for
    abstained — an option menu this loop has no rule for

and the pane, at that moment:

    Do you want to make this edit to plan0.md?
    ❯ 1. Yes
      2. Yes, allow all edits in tsk_3ab4aa7b7b/ during this session
      3. No

That gate has a rule. `_PLAN_WRITE` matches `edit … plan0.md` precisely, and the
loop answers it — *"writing this task's own plan file, which is exactly what it
was asked to do"* — one pass earlier, in the same run. What changed between the
two passes is not the screen. It is the **record**: `collect_plan` had moved the
task to `awaiting-grant`, and `_gate` is handed `planning=(state == PLANNING)`.

So the allowance evaporates the instant the plan is collected, while the session
is still finishing the edits that produced it. The task then sits at a gate the
loop is entitled to answer and has just forgotten how to, and every remaining
pass abstains.

**The state is not the boundary; the release is.** Writing `plan0.md` is what the
session was asked to do, and it stays exactly that until the owner releases the
task and the work begins — which is the same line the ceiling uses (planning
runs at A0, `release` raises it) and the same line the criteria-drift exemption
uses. Keying on `state == PLANNING` has now been wrong in both directions: the
budget keyed on it and fired late because a task *sits* in `planning` while its
session works; this keyed on it and stopped early because a session keeps
planning after the record has moved on.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (operator as op, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, worker as wk)

#: The real gate, verbatim from the live pane.
PLAN_EDIT_GATE = (
    " 62  ## Permissions needed\n"
    "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
    " Do you want to make this edit to plan0.md?\n"
    " ❯ 1. Yes\n"
    "   2. Yes, allow all edits in tsk_3ab4aa7b7b/ during this session (shift+tab)\n"
    "   3. No\n"
    "\n"
    " Esc to cancel · Tab to amend\n"
)

PLAN = """# write the report

## Phase 1 — write it
Do the thing.
Verified when: out.txt exists

## Permissions needed
- write out.txt
"""


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


# ── the gate itself ───────────────────────────────────────────────────

def test_the_loop_answers_it_while_the_record_says_planning():
    """The pass that worked. Unchanged."""
    got = op._gate(PLAN_EDIT_GATE, planning=True)
    assert got is not None and got[0] == "1"


def test_and_still_answers_it_once_the_plan_is_collected(config, agent):
    """The pass that did not. The screen is identical; only the record moved."""
    got = op._gate(PLAN_EDIT_GATE, planning=False, released=False)
    assert got is not None and got[0] == "1"


def test_but_not_once_the_owner_has_released_it(config, agent):
    """After release the plan is settled and the work has begun. A session
    editing the standard it is about to be judged against is the owner's
    business, not the loop's."""
    got = op._gate(PLAN_EDIT_GATE, planning=False, released=True)
    assert got is not None and got[0] is None


# ── through a whole pass ──────────────────────────────────────────────

class Pane:
    def __init__(self, screen):
        self.screen = screen
        self.sent = []

    def capture(self, name):
        return self.screen

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def key(self, name, key):
        return {"ok": True}


class Runtime:
    engine = "claude"

    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text, **kw):
        return {"ok": True}

    def stop(self, name):
        return {"ok": True}


    def set_ceiling(self, name, ceiling):
        """Part of the runtime contract — a double omitting it was hidden by a
        swallowed exception in `release` until that stopped being swallowed."""
        return {"name": name, "ceiling": ceiling}

def _awaiting(config, agent):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.create(config, agent, d)
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(PLAN)
    t = tsk.attach_plan(config, agent, t, pl.parse(PLAN))
    # `attach_plan` fills `awaiting` from the plan's declared permissions, and
    # `assign` refuses a task that is still waiting on one. Cleared to get the
    # session started, then set back — the state under test is the one AFTER
    # the plan came back and before the owner granted.
    t.awaiting = []
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    t.plan_agreed = True
    # Delivered during planning; `release` is what sets the WORK brief. A task
    # sitting at awaiting-grant owes the session nothing.
    t.kickoff_pending = None
    t.state = tsk.AWAITING_GRANT
    t.awaiting = ["write out.txt"]
    return tsk._touch(agent, t, time.time)


def test_a_pass_on_an_awaiting_task_answers_the_plan_edit(config, agent):
    t = _awaiting(config, agent)
    pane = Pane(PLAN_EDIT_GATE)
    act = op.tick(config, agent, t, pane=pane, now=time.time)
    assert act.kind == "answered", act
    assert pane.sent == ["1"]


# ── and the loop hands back rather than spinning ──────────────────────

def test_supervising_stops_when_the_task_waits_on_the_owner(config, agent):
    """`awaiting-grant` means the owner has to run `sarsi grant`. There is
    nothing the loop can do, and the passes it spends discovering that are
    passes it spends not returning control."""
    t = _awaiting(config, agent)
    t.awaiting = ["write out.txt"]
    tsk._touch(agent, t, time.time)
    seen = op.run(config, agent, t, pane=Pane("❯ \n"), passes=5,
                  interval=0, sleep=lambda s: None)
    assert len(seen) == 1, [a.kind for a in seen]
    assert seen[0].kind == "awaiting-grant"


def test_and_says_what_the_owner_has_to_grant(config, agent):
    t = _awaiting(config, agent)
    seen = op.run(config, agent, t, pane=Pane("❯ \n"), passes=2,
                  interval=0, sleep=lambda s: None)
    assert "grant" in seen[0].detail.lower()


def test_a_released_task_is_supervised_as_before(config, agent):
    """The guard must not stop a run that is actually working."""
    t = _awaiting(config, agent)
    t.state = tsk.RUNNING
    t.awaiting = []
    t.work_started_at = time.time()
    tsk._touch(agent, t, time.time)
    seen = op.run(config, agent, t, pane=Pane("❯ \n"), passes=3,
                  interval=0, sleep=lambda s: None)
    assert len(seen) == 3


# ── "released" has to mean the owner released ─────────────────────────
#
# The live fix did not take, and the record said why:
#
#     state: awaiting-grant   work_started_at: 1785957183.28
#
# on a task nobody had released. `attach_plan` sets `work_started_at` — the
# comment beside it is explicit that it must, because *"release is an owner
# command the loop never calls, so anchoring the boundary only there would
# leave most tasks with the work budget still paying for planning"*. It marks
# where PLANNING ENDED, which is what the budget needs and is not an owner act
# at all.
#
# So a marker set only by `release` is needed for the questions that are about
# the OWNER having acted. The budget keeps the one it has.


def test_planning_ending_is_not_the_owner_releasing(config, agent):
    """The confusion that made the live fix a no-op."""
    t = _awaiting(config, agent)
    t.work_started_at = time.time()           # what `adopt_plan` does
    assert t.released_at is None              # and nobody released it


def test_release_is_what_sets_it(config, agent):
    t = _awaiting(config, agent)
    t.awaiting = []                           # granted
    t.state = tsk.READY
    tsk._touch(agent, t, time.time)
    t = ses.release(config, agent, t, runtime=Runtime())
    assert t.released_at is not None


def test_the_gate_reads_the_owner_s_marker(config, agent):
    """A task the loop moved out of planning still runs at A0 — its ceiling is
    fixed at `assign` and only `release` raises it — so the A0 allowances still
    apply."""
    t = _awaiting(config, agent)
    pane = Pane(PLAN_EDIT_GATE)
    act = op.tick(config, agent, t, pane=pane, now=time.time)
    assert act.kind == "answered", act
    assert pane.sent == ["1"]


def test_and_stops_reading_it_once_the_owner_has(config, agent):
    t = _awaiting(config, agent)
    t.released_at = time.time()
    tsk._touch(agent, t, time.time)
    pane = Pane(PLAN_EDIT_GATE)
    act = op.tick(config, agent, t, pane=pane, now=time.time)
    assert act.kind == "abstained", act
