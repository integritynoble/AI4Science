"""A verified task lets go of its session.

`attention` on grace, straight after a PASS:

    [orphan] sarsi-worker/tsk_57e6d75b2f
        its task is verified but session sarsi-worker-5b2f is still running,
        holding whatever it was granted

The board was right and nothing acted on it. The work was done, judged and
recorded, and the terminal stayed up **holding the grants the owner gave it for
that work** — a live Claude Code session, at the released ceiling, with write
permission to the working directory and no task left that needs any of it. Every
one of those grants was justified by a piece of work that has finished.

It also costs the worker a concurrency slot, so a fleet that verifies ten tasks
and stops none of them is a fleet that can no longer start anything.

Three things this must NOT do:

  * **it must not turn the task off.** `stop` exists and sets the state to
    `off`, which would erase the one outcome worth keeping. The session closes;
    the verdict, the plan and the record stay exactly as they are.
  * **it must not fire on a PHASE passing.** A phase verdict is the loop's own
    checkpoint mid-run — closing the session there would end the task at its
    first passing phase.
  * **it must not take the wheel from the owner.** If someone is attached and
    steering, the session is theirs until they hand it back, verdict or no
    verdict.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)

PLAN = """# write the report

## Phase 1 — write it
Do the thing.
Verified when: out.txt exists

## Phase 2 — check it
Look again.
Verified when: out.txt contains 42

## Permissions needed
- none
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


class Runtime:
    engine = "claude"

    def __init__(self, *, can_stop=True):
        self.stopped = []
        self.sent = []
        self._can_stop = can_stop

    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text, **kw):
        self.sent.append(text)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {}

    if True:
        def stop(self, name):
            if not self._can_stop:
                raise OSError("tmux is gone")
            self.stopped.append(name)
            return {"ok": True}


def _passing(**kw):
    return {"state": "PASS", "why": "it is all there"}


def _failing(**kw):
    return {"state": "FAIL", "why": "not yet"}


def _task(config, agent, rt):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.create(config, agent, d)
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(PLAN)
    t = tsk.attach_plan(config, agent, t, pl.parse(PLAN))
    t.plan_agreed = True
    t = ses.assign(config, agent, t, runtime=rt, installed=lambda: set())
    t.work_started_at = time.time()
    return tsk._touch(agent, t, time.time)


# ── it lets go ────────────────────────────────────────────────────────

def test_the_session_is_closed_when_the_task_verifies(config, agent):
    rt = Runtime()
    t = _task(config, agent, rt)
    name = t.session["name"]
    t = ses.verify(config, agent, t, verifier=_passing, evidence="out.txt: 42",
                   runtime=rt, now=time.time)
    assert t.state == tsk.VERIFIED
    assert rt.stopped == [name]


def test_and_the_record_no_longer_claims_a_live_one(config, agent):
    """`attention` reads this field to decide whether a terminal is orphaned."""
    rt = Runtime()
    t = _task(config, agent, rt)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=rt, now=time.time)
    assert t.session is None


def test_but_what_it_cost_is_kept(config, agent):
    """`spend` reads the working directory from the session record to find the
    transcript. A total that fell when a task SUCCEEDED is the one thing a
    spend figure must never do."""
    rt = Runtime()
    t = _task(config, agent, rt)
    cwd = t.session["cwd"]
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=rt, now=time.time)
    assert [s.get("cwd") for s in t.past_sessions] == [cwd]


def test_the_verdict_and_the_state_survive(config, agent):
    """`stop` sets the state to `off`, which would erase the outcome. This is
    not that."""
    rt = Runtime()
    t = _task(config, agent, rt)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=rt, now=time.time)
    reloaded = tsk.get(config, agent, t.id)
    assert reloaded.state == tsk.VERIFIED
    assert (reloaded.verdict or {}).get("state") == "PASS"


def test_a_tmux_that_will_not_die_does_not_lose_the_verdict(config, agent):
    """Best-effort, like `stop`: the cleanup failing must not cost the record
    of work that was actually verified."""
    rt = Runtime(can_stop=False)
    t = _task(config, agent, rt)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=rt, now=time.time)
    assert t.state == tsk.VERIFIED


# ── and only then ─────────────────────────────────────────────────────

def test_a_failing_task_keeps_its_session(config, agent):
    """A FAIL is handed back for another attempt. Closing the session would
    make every failure terminal."""
    rt = Runtime()
    t = _task(config, agent, rt)
    t = ses.verify(config, agent, t, verifier=_failing, evidence="e",
                   runtime=rt, now=time.time)
    assert t.session is not None
    assert rt.stopped == []


def test_a_phase_passing_keeps_its_session(config, agent):
    """A phase verdict is a checkpoint mid-run. Closing here would end the task
    at its first passing phase."""
    rt = Runtime()
    t = _task(config, agent, rt)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=rt, phase=0, now=time.time)
    assert t.session is not None
    assert rt.stopped == []


def test_the_owner_at_the_wheel_keeps_it(config, agent):
    """Interact hands steering to the owner. Killing their terminal because a
    verdict landed would take it out from under them mid-keystroke."""
    rt = Runtime()
    t = _task(config, agent, rt)
    t.steering_paused = True
    tsk._touch(agent, t, time.time)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=rt, now=time.time)
    assert t.state == tsk.VERIFIED
    assert rt.stopped == []
    assert t.session is not None


# ── the board stops reporting it ──────────────────────────────────────

def test_attention_no_longer_calls_it_an_orphan(config, agent):
    from ai4science.harness.agents.sarsi import attention as att

    rt = Runtime()
    t = _task(config, agent, rt)
    name = t.session["name"]
    ses.verify(config, agent, t, verifier=_passing, evidence="e", runtime=rt,
               now=time.time)
    got = att.needs(config, agent, pane=_Pane(), live=lambda: {name})
    assert [i for i in got.items if i.kind == "orphan"] == []


class _Pane:
    def capture(self, name):
        return "❯ \n"


# ── the record still names what did the work ──────────────────────────

def test_a_verified_task_still_names_the_session_that_did_it(config, agent):
    """A pre-existing test asserts this and it is right: "session X, verdict
    PASS" is how the record says WHICH run produced the result. Closing the
    terminal must not take that with it — the mechanism changed, the
    requirement did not."""
    rt = Runtime()
    t = _task(config, agent, rt)
    name = t.session["name"]
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=rt, now=time.time)
    assert t.session is None
    assert name in ses.answer(config, agent, t)


def test_and_a_task_that_never_had_one_says_nothing(config, agent):
    """`or "no session"` once produced `session no session, verdict PASS`.
    Where there is no session there is no clause."""
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                        pl.parse(PLAN))
    t.verdict = {"state": "PASS", "why": "done"}
    t.state = tsk.VERIFIED
    assert "session" not in ses.answer(config, agent, t)
