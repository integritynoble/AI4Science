"""Planning runs at **A0**, and the ceiling rises only when the owner releases it.

The live run for abraham exposed the gap: the session was told to plan and stop,
and wrote its artefact during the planning phase anyway. "Stop" was a sentence in
a prompt, and a sentence is not a gate — at A1 a session may write freely in its
own folder, so nothing held the work back until the owner had seen what the plan
declared.

So the ceiling does the holding:

  * **planning runs at `A0`** — reads allowed, everything else asks;
  * **release raises it** to whatever that agent has earned;
  * and because A0 also gates writing `plan0.md`, `AN` learns exactly one new
    gate: **writing this task's own plan file, while planning**. Narrow on
    purpose — it is the one write the worker explicitly asked for.

The narrowness is the point. A blanket "allow writes while planning" would make
A0 decorative, which is worse than not dropping it at all.
"""
import pytest

from ai4science.harness.agents.sarsi import (operator as op, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path / "cp"))
    monkeypatch.setenv("PWM_TRUST_OWNER", "tester")
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    a = config.agents["work"]
    a.ceiling = "A2"
    return a


class FakeRuntime:
    engine = "claude"

    def __init__(self):
        self.started, self.sent, self.ceilings = [], [], []

    def start(self, name, cwd, *, govern, ceiling, env=None):
        self.started.append(ceiling)
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        self.ceilings.append(ceiling)
        return {"ok": True}


def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    return tsk.create(config, agent, d)


GOOD_PLAN = """\
# finish the export

## Phase 1 — do it
Verified when: export.csv exists

## Permissions needed
- none
"""


# ── the drop ──────────────────────────────────────────────────────────

def test_a_planning_session_starts_at_a0(config, agent):
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.started == ["A0"]


def test_the_task_records_that_it_is_planning_at_a0(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert t.session["ceiling"] == "A0"


def test_an_agreed_plan_starts_at_the_agents_own_ceiling(config, agent):
    """Nothing changes for a task whose plan is already settled."""
    t = _task(config, agent)
    t = tsk.attach_plan(config, agent, t,
                        pl.Plan(goal="g", phases=[pl.Phase(title="x",
                                                           verified_when="y")]))
    t.plan_agreed = True
    rt = FakeRuntime()
    ses.assign(config, agent, tsk._touch(agent, t, __import__("time").time),
               runtime=rt)
    assert rt.started == ["A2"]


# ── the raise ─────────────────────────────────────────────────────────

def _planned(config, agent, rt):
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(GOOD_PLAN)
    return ses.collect_plan(config, agent, t, runtime=rt, session_idle=True)


def test_release_raises_the_ceiling(config, agent):
    rt = FakeRuntime()
    t = ses.release(config, agent, _planned(config, agent, rt), runtime=rt)
    assert rt.ceilings == ["A2"]
    assert t.session["ceiling"] == "A2"


def test_release_raises_only_to_what_was_earned(config, agent):
    """A3 in the registry is still capped until the trust ledger says so."""
    agent.ceiling = "A3"
    rt = FakeRuntime()
    ses.release(config, agent, _planned(config, agent, rt), runtime=rt)
    assert rt.ceilings == ["A2"]


def test_an_ungranted_task_never_gets_the_raise(config, agent):
    rt = FakeRuntime()
    t = _planned(config, agent, rt)
    t.awaiting = ["write /somewhere"]
    with pytest.raises(ses.NotReady):
        ses.release(config, agent, t, runtime=rt)
    assert rt.ceilings == []


# ── the one gate A0 needs answered ────────────────────────────────────

PLAN_WRITE_GATE = """\
 Claude wants to create plan0.md

 ❯ 1. Yes
   2. No, and tell Claude what to do differently
"""

OTHER_WRITE_GATE = """\
 Claude wants to create export.csv

 ❯ 1. Yes
   2. No, and tell Claude what to do differently
"""

COMMAND_GATE = """\
 Claude wants to run: rm -rf build/

 ❯ 1. Yes
   2. No, and tell Claude what to do differently
"""


class Pane:
    def __init__(self, text):
        self.text, self.sent, self.keys = text, [], []

    def capture(self, name):
        return self.text

    def send(self, name, text):
        self.sent.append(text)

    def key(self, name, key):
        self.keys.append(key)


def _planning_task(config, agent):
    rt = FakeRuntime()
    return ses.assign(config, agent, _task(config, agent), runtime=rt)


def test_writing_the_plan_file_while_planning_is_answered(config, agent):
    pane = Pane(PLAN_WRITE_GATE)
    action = op.tick(config, agent, _planning_task(config, agent), pane=pane)
    assert action.kind == "answered"
    assert pane.sent == ["1"]


def test_writing_anything_else_while_planning_is_not(config, agent):
    """A blanket 'allow writes while planning' would make A0 decorative."""
    pane = Pane(OTHER_WRITE_GATE)
    action = op.tick(config, agent, _planning_task(config, agent), pane=pane)
    assert action.kind == "abstained" and pane.sent == []


def test_running_a_command_while_planning_is_not(config, agent):
    pane = Pane(COMMAND_GATE)
    assert op.tick(config, agent, _planning_task(config, agent),
                   pane=pane).kind == "abstained"


def test_the_plan_write_gate_is_not_answered_once_work_has_started(config, agent):
    """Outside planning it is an ordinary edit and belongs to the owner."""
    rt = FakeRuntime()
    t = _planned(config, agent, rt)
    t = ses.release(config, agent, t, runtime=rt)
    pane = Pane(PLAN_WRITE_GATE)
    assert op.tick(config, agent, t, pane=pane).kind == "abstained"
