"""Closing a task — the gap that wedges a board.

`turn_off` and `resume` existed, but nothing reached them: no CLI verb, no chat
verb. So a finished task kept its concurrency slot forever, and the only way to
free one was `rm -rf` on the task directory — deleting the plan, the verdict and
the history, outside any command, with no record that it happened.

Three states, and the difference between them is the whole point:

  * **`off`** — stopped, resumable. The plan survives; the slot is freed.
  * **`archived`** — terminal. The record is kept and the slot is freed, but it
    is off the default board and cannot be resumed by accident.
  * **deleted** — still not a thing a worker does. A task never disappears.

And stopping a task **kills its session**. A stopped task whose tmux session
keeps running is the worst of both: the board says nothing is happening while
something is.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk, worker)


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
        self.started, self.stopped, self.sent = [], [], []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
        self.started.append(name)
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def stop(self, name):
        self.stopped.append(name)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.start(config, agent, t)


# ── archive: terminal, kept, and off the board ────────────────────────

def test_archiving_keeps_the_record(config, agent):
    t = tsk.archive(config, agent, _task(config, agent))
    kept = tsk.get(config, agent, t.id)
    assert kept is not None and kept.goal == "finish the export"


def test_an_archived_task_is_not_on_the_default_board(config, agent):
    t = tsk.archive(config, agent, _task(config, agent))
    assert [x.id for x in tsk.all_of(config, agent)] == []


def test_an_archived_task_is_listed_when_asked_for(config, agent):
    t = tsk.archive(config, agent, _task(config, agent))
    assert [x.id for x in tsk.all_of(config, agent, archived=True)] == [t.id]


def test_archiving_frees_the_concurrency_slot(config, agent):
    """The observed failure: a full board refusing every new directive."""
    agent.max_concurrent_tasks = 1
    first = _task(config, agent, "job one")
    blocked = _task(config, agent, "job two")
    assert blocked.blocked_by == "concurrency"

    tsk.archive(config, agent, first)
    started = tsk.start(config, agent, tsk.get(config, agent, blocked.id))
    assert started.state == tsk.RUNNING and started.blocked_by is None


def test_an_archived_task_does_not_resume_by_accident(config, agent):
    t = tsk.archive(config, agent, _task(config, agent))
    with pytest.raises(tsk.Archived):
        tsk.resume(config, agent, tsk.get(config, agent, t.id))


# ── stop: resumable, and it takes the session with it ─────────────────

def test_stopping_frees_the_slot_and_keeps_the_plan(config, agent):
    t = tsk.turn_off(config, agent, _task(config, agent))
    assert t.state == tsk.OFF
    assert tsk.read_plan(config, agent, tsk.get(config, agent, t.id)) is not None


def test_stopping_kills_the_session(config, agent):
    """A stopped task whose session keeps running is the worst of both: the
    board says nothing is happening while something is."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    name = t.session["name"]
    t = ses.stop(config, agent, t, runtime=rt)
    assert rt.stopped == [name]
    assert tsk.get(config, agent, t.id).session is None


def test_stopping_a_task_with_no_session_is_not_an_error(config, agent):
    rt = FakeRuntime()
    t = ses.stop(config, agent, _task(config, agent), runtime=rt)
    assert t.state == tsk.OFF and rt.stopped == []


def test_a_stopped_task_resumes(config, agent):
    t = tsk.turn_off(config, agent, _task(config, agent))
    back = tsk.resume(config, agent, tsk.get(config, agent, t.id))
    assert back.state == tsk.RUNNING


# ── a verified task should not hold a slot either ─────────────────────

def test_a_verified_task_does_not_occupy_a_slot(config, agent):
    """It is finished. Holding a slot for it wedges the board just as surely."""
    agent.max_concurrent_tasks = 1
    first = _task(config, agent, "job one")
    tsk.finish(config, agent, first, verdict={"verdict": "PASS", "reason": "done"})
    second = _task(config, agent, "job two")
    assert second.state == tsk.RUNNING


# ── the surfaces: chat ────────────────────────────────────────────────

from ai4science.harness.agents.sarsi import chat


def _say(config, agent, text, runtime=None):
    return chat.handle(config, agent, text, surface="cli",
                       runtime=runtime or FakeRuntime())


def test_chat_stop_stops_the_task(config, agent):
    t = _task(config, agent)
    out = _say(config, agent, f"/stop {t.id}")
    assert tsk.get(config, agent, t.id).state == tsk.OFF
    assert "stopped" in out.lower()


def test_chat_stop_kills_the_session(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/stop {t.id}", runtime=rt)
    assert rt.stopped == [t.session["name"]]


def test_chat_archive_takes_it_off_the_board(config, agent):
    t = _task(config, agent)
    _say(config, agent, f"/archive {t.id}")
    assert "no tasks" in _say(config, agent, "/tasks").lower()


def test_chat_reopen_puts_it_back_stopped_not_running(config, agent):
    """Re-opening is the owner's decision to look again, not to start work."""
    t = _task(config, agent)
    _say(config, agent, f"/archive {t.id}")
    _say(config, agent, f"/reopen {t.id}")
    assert tsk.get(config, agent, t.id).state == tsk.OFF


def test_the_board_says_how_many_are_archived(config, agent):
    """Otherwise the record is invisible and looks like it was deleted."""
    t = _task(config, agent)
    _say(config, agent, f"/archive {t.id}")
    assert "archived" in _say(config, agent, "/tasks").lower()


def test_stopping_an_unknown_task_says_so(config, agent):
    assert "no task" in _say(config, agent, "/stop tsk_nothing").lower()
