"""Changing the goal, not just the criteria.

`/edit <task> <n> <criterion>` changes what gets **verified**. The goal itself
was fixed at creation, so "make the plan and the goal together with the user"
was only half possible: the owner could move the finish line but never the race.

What moving a goal has to do, and what it must not:

  * **the plan follows the goal.** A plan drafted for the old goal, still
    attached to the new one, is a plan that verifies the wrong thing — the most
    expensive kind of wrong, because it looks settled.
  * **the owner's edited criteria survive.** They are the owner's words about
    what "done" means; a re-draft may propose around them, never over them.
  * **a running session is told.** Changing the goal under a working session and
    not saying so is how it finishes the old task perfectly.
  * **an empty goal is refused**, like any other directive with nothing in it.
"""
import pytest

from ai4science.harness.agents.sarsi import (chat, plan as pl, registry as reg,
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


def _say(config, agent, text, runtime=None):
    return chat.handle(config, agent, text, surface="cli",
                       runtime=runtime or FakeRuntime())


# ── the goal moves ────────────────────────────────────────────────────

def test_goal_changes_the_goal(config, agent):
    t = _task(config, agent)
    _say(config, agent, f"/goal {t.id} finish the export and mail it to me")
    assert tsk.get(config, agent, t.id).goal == "finish the export and mail it to me"


def test_the_reply_states_the_new_goal(config, agent):
    t = _task(config, agent)
    out = _say(config, agent, f"/goal {t.id} rebuild the index")
    assert "rebuild the index" in out


def test_an_empty_goal_is_refused(config, agent):
    t = _task(config, agent)
    out = _say(config, agent, f"/goal {t.id}")
    assert "usage" in out.lower()
    assert tsk.get(config, agent, t.id).goal == "finish the export"


def test_the_directive_records_the_new_goal_too(config, agent):
    """The directive is what a re-draft reads; leaving it stale re-drafts the
    old goal the moment anything touches the plan."""
    t = _task(config, agent)
    _say(config, agent, f"/goal {t.id} rebuild the index")
    after = tsk.get(config, agent, t.id)
    assert after.directive.get("goal") == "rebuild the index"


# ── the plan follows it ───────────────────────────────────────────────

def test_the_plan_is_redrafted_for_the_new_goal(config, agent):
    t = _task(config, agent)
    _say(config, agent, f"/goal {t.id} rebuild the search index")
    plan = tsk.read_plan(config, agent, tsk.get(config, agent, t.id))
    assert "rebuild the search index" in plan.render()


def test_the_plan_is_no_longer_agreed_after_the_goal_moves(config, agent):
    """It was agreed about a different goal. Saying so is what sends it back
    through the planning handshake instead of straight to work."""
    t = _task(config, agent)
    t.plan_agreed = True
    tsk._touch(agent, t, __import__("time").time)
    _say(config, agent, f"/goal {t.id} rebuild the search index")
    assert tsk.get(config, agent, t.id).plan_agreed is False


def test_the_owners_edited_criteria_are_kept(config, agent):
    """A re-draft may propose around the owner's words, never over them."""
    t = _task(config, agent)
    _say(config, agent, f"/edit {t.id} 1 the console reports zero queued")
    _say(config, agent, f"/goal {t.id} rebuild the search index")
    after = tsk.get(config, agent, t.id)
    assert "the console reports zero queued" in after.criteria
    assert after.plan_owner_edited is True


# ── a working session is told ─────────────────────────────────────────

def test_a_running_session_is_told_the_goal_moved(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/goal {t.id} rebuild the search index", runtime=rt)
    assert "rebuild the search index" in rt.sent[-1]


def test_a_task_with_no_session_changes_quietly(config, agent):
    rt = FakeRuntime()
    t = _task(config, agent)
    _say(config, agent, f"/goal {t.id} rebuild the search index", runtime=rt)
    assert rt.sent == []


def test_the_owner_may_move_the_goal_while_holding_the_wheel(config, agent):
    """Interact pauses the WORKER's steering, not the owner's own word."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/interact {t.id}", runtime=rt)
    out = _say(config, agent, f"/goal {t.id} rebuild the search index", runtime=rt)
    assert tsk.get(config, agent, t.id).goal == "rebuild the search index"
    assert "rebuild the search index" in out
