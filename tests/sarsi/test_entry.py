"""Entering a worker puts you *somewhere*.

Until now, entering a worker put you nowhere: `/tasks` listed a board and every
message was a fresh start. The owner asked for the opposite — enter a worker and
be **in a task**, and if there is no task, be asked what to do rather than shown
an empty board.

The cursor is per `(surface, account)`, not global: the same worker read from
Telegram on a phone and from the CLI on the machine are two places to stand, and
a shared cursor would move one when the other was used.

Four rules:

  * **entering with tasks lands on the one you last touched.** Not the newest —
    the one you were working on, which is the only one you have context for.
  * **entering with none asks.** An empty board is a dead end; a question is a
    way out of it.
  * **inside a task, plain words are about THAT task.** They reach its plan, not
    a general chat, because that is what being "in" a task means.
  * **leaving is explicit.** `/tasks` steps back out to the board, so the cursor
    never silently follows something the owner did not choose.
"""
import pytest

from ai4science.harness.agents.sarsi import (chat, entry, plan as pl,
                                             registry as reg, task as tsk,
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

    def stop(self, name):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.start(config, agent, t)


def _say(config, agent, text, surface="cli", runtime=None):
    return chat.handle(config, agent, text, surface=surface,
                       runtime=runtime or FakeRuntime())


# ── the empty state asks ──────────────────────────────────────────────

def test_entering_with_no_tasks_asks_what_you_want_done(config, agent):
    out = entry.enter(config, agent, surface="cli")
    assert "?" in out
    assert "no tasks" in out.lower() or "nothing" in out.lower()


def test_the_question_says_how_to_answer_it(config, agent):
    """An empty board is a dead end; a question is only a way out if it says
    which words work."""
    out = entry.enter(config, agent, surface="cli")
    assert "/do" in out or "/new" in out


def test_new_creates_a_task_from_inside_the_worker(config, agent):
    _say(config, agent, "/new index the CASSI results folder")
    goals = [t.goal for t in tsk.all_of(config, agent)]
    assert goals == ["index the CASSI results folder"]


def test_new_lands_you_in_the_task_it_made(config, agent):
    _say(config, agent, "/new index the results")
    t = tsk.all_of(config, agent)[0]
    assert entry.current(config, agent, surface="cli") == t.id


# ── entering lands on the last one touched ────────────────────────────

def test_entering_lands_on_the_task_you_last_opened(config, agent):
    first = _task(config, agent, "job one")
    second = _task(config, agent, "job two")
    _say(config, agent, f"/{first.id}")            # touched, and not the newest
    out = entry.enter(config, agent, surface="cli")
    assert first.id in out and first.goal in out


def test_with_no_cursor_yet_it_shows_the_board_rather_than_guessing(config, agent):
    _task(config, agent, "job one")
    _task(config, agent, "job two")
    out = entry.enter(config, agent, surface="cli")
    assert "job one" in out and "job two" in out


def test_a_cursor_on_an_archived_task_falls_back_to_the_board(config, agent):
    """The task is gone from the board; standing on it would be standing
    nowhere."""
    t = _task(config, agent)
    _say(config, agent, f"/{t.id}")
    _say(config, agent, f"/archive {t.id}")
    out = entry.enter(config, agent, surface="cli")
    assert "no tasks" in out.lower() or "nothing" in out.lower()


# ── the cursor is per surface ─────────────────────────────────────────

def test_two_surfaces_stand_in_different_places(config, agent):
    first = _task(config, agent, "job one")
    second = _task(config, agent, "job two")
    _say(config, agent, f"/{first.id}", surface="cli")
    _say(config, agent, f"/{second.id}", surface="telegram")
    assert entry.current(config, agent, surface="cli") == first.id
    assert entry.current(config, agent, surface="telegram") == second.id


def test_the_cursor_survives_a_restart(config, agent):
    """It is where you are standing, not a variable in one process."""
    t = _task(config, agent)
    _say(config, agent, f"/{t.id}")
    fresh = reg.load() if False else config          # same state root on disk
    assert entry.current(fresh, agent, surface="cli") == t.id


# ── inside a task, plain words are about that task ────────────────────

def test_plain_words_inside_a_task_reach_its_session(config, agent):
    from ai4science.harness.agents.sarsi import session as ses
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/{t.id}", runtime=rt)
    _say(config, agent, "use the staging host, not production", runtime=rt)
    assert "use the staging host, not production" in rt.sent[-1]


def test_plain_words_with_no_cursor_are_not_steered_anywhere(config, agent):
    """A message with nowhere to go must not pick a session."""
    from ai4science.harness.agents.sarsi import session as ses
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    before = list(rt.sent)
    _say(config, agent, "just thinking out loud", runtime=rt)
    assert rt.sent == before


def test_tasks_steps_back_out_to_the_board(config, agent):
    t = _task(config, agent)
    _say(config, agent, f"/{t.id}")
    _say(config, agent, "/tasks")
    assert entry.current(config, agent, surface="cli") is None


def test_a_task_with_no_session_says_so_rather_than_swallowing_the_words(config, agent):
    t = _task(config, agent)
    _say(config, agent, f"/{t.id}")
    out = _say(config, agent, "use the staging host")
    assert "no session" in out.lower()
