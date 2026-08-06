"""A pane that could not be read is not a pane that is gone.

`TmuxPane.capture` already draws this line and says why:

    The pane's text, or **None** when there is no such pane. Not `""`. "The
    pane is gone" and "the pane is empty" were the same string, so a session
    whose terminal had died read as a quiet one.

`None` means gone. Two callers then wrapped the call in `except Exception:
screen = None`, which folds a **third** state — the reader itself broke — into
the one that means gone, and each goes on to report a fact it does not have:

* `attention._from_pane` reports **`dead-session`**: *"its record points at
  session X, which is not there"*. It is there, as far as anyone knows; nobody
  could look.
* `questions` treats an unreadable screen as "the answer did not land", so it
  retypes — up to `MAX_TRIES` — and then raises `NotDelivered`. Two harms at
  once: the same answer typed three times into a session that may have had it
  the first time, and a report that delivery failed when delivery was never
  checked.

Both are the rule this system applies everywhere else, missing from one place:
**unknown is not zero.** `blast` counts unchecked commands rather than calling
them clean, `spend` says what it could not measure, `budget` reads an unreadable
step count as unenforced. A pane is the same: not-observed is not not-there.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (attention as att, plan as pl,
                                             questions as qs, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)

BODY = "# g\n\n## Phase 1 — do it\nVerified when: out.md exists\n"


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

    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text, **kw):
        return {"ok": True}

    def stop(self, name):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"name": name, "ceiling": ceiling}


class Gone:
    """tmux answered, and there is no such pane."""
    def capture(self, name):
        return None

    def send(self, name, text):
        return {"ok": True}

    def key(self, name, key):
        return {"ok": True}


class Unreadable(Gone):
    """The reader itself broke — a permission error, a timeout, a bad object."""
    def capture(self, name):
        raise OSError("tmux: connection timed out")


def _asked(config, agent, task, text="which directory?"):
    """Open a question the way the loop does — a ledger `asked` report."""
    from ai4science.harness.agents.sarsi import ledger
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": qs.ASKED,
                   "evidence": [f"Q: {text}"]}, now=time.time)
    return task


def _running(config, agent):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.create(config, agent, d)
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(BODY)
    t = tsk.attach_plan(config, agent, t, pl.parse(BODY))
    t.awaiting = []
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    t.state = tsk.RUNNING
    t.kickoff_pending = None
    return tsk._touch(agent, t, time.time)


# ── attention: gone and unreadable are different items ────────────────

def test_a_pane_that_is_gone_is_still_a_dead_session(config, agent):
    """Unchanged. tmux answered and there is no pane — the record is stale and
    the owner should close it."""
    t = _running(config, agent)
    kinds = [i.kind for i in att.needs(config, agent, pane=Gone(),
                                       live=lambda: set()).items]
    assert "dead-session" in kinds


def test_but_a_pane_that_would_not_read_is_not(config, agent):
    t = _running(config, agent)
    items = att.needs(config, agent, pane=Unreadable(), live=lambda: set()).items
    assert "dead-session" not in [i.kind for i in items]
    assert "unreadable" in [i.kind for i in items], items


def test_and_it_says_nobody_could_look(config, agent):
    t = _running(config, agent)
    item = [i for i in att.needs(config, agent, pane=Unreadable(),
                                 live=lambda: set()).items
            if i.kind == "unreadable"][0]
    detail = item.detail.lower()
    assert "could not" in detail or "unknown" in detail
    assert "connection timed out" in detail        # the cause, not just the fact


def test_it_does_not_claim_the_session_is_gone(config, agent):
    t = _running(config, agent)
    item = [i for i in att.needs(config, agent, pane=Unreadable(),
                                 live=lambda: set()).items
            if i.kind == "unreadable"][0]
    assert "is not there" not in item.detail


def test_an_ended_task_with_an_unreadable_pane_still_says_something(config, agent):
    """A gone pane on an ENDED task is silence — the record and the machine
    agree. An unreadable one on an ended task agrees about nothing."""
    t = _running(config, agent)
    t.state = tsk.VERIFIED
    tsk._touch(agent, t, time.time)
    kinds = [i.kind for i in att.needs(config, agent, pane=Unreadable(),
                                       live=lambda: set()).items]
    assert "unreadable" in kinds


# ── questions: unconfirmed is not undelivered ─────────────────────────

def test_an_unreadable_screen_does_not_become_not_delivered(config, agent):
    t = _asked(config, agent, _running(config, agent))
    with pytest.raises(qs.NotConfirmed) as e:
        qs.answer(config, agent, t, "which directory?", "use /tmp",
                  pane=Unreadable(), runtime=Runtime(), now=time.time)
    assert "could not" in str(e.value).lower()


def test_and_it_is_typed_once_not_three_times(config, agent):
    """Retyping because nobody could read is how one answer becomes three in a
    session that may have had it the first time."""
    class Counting(Unreadable):
        def __init__(self):
            self.typed = 0

        def send(self, name, text):
            self.typed += 1
            return {"ok": True}

    pane = Counting()
    t = _asked(config, agent, _running(config, agent))
    with pytest.raises(qs.NotConfirmed):
        qs.answer(config, agent, t, "which directory?", "use /tmp",
                  pane=pane, runtime=Runtime(), now=time.time)
    assert pane.typed <= 1, pane.typed


def test_a_readable_screen_that_never_shows_it_is_still_not_delivered(config,
                                                                      agent):
    """The distinction has to cut both ways, or it is just a wider excuse."""
    class Blank(Gone):
        def capture(self, name):
            return "❯ \n"

    t = _asked(config, agent, _running(config, agent))
    with pytest.raises(qs.NotDelivered):
        qs.answer(config, agent, t, "which directory?", "use /tmp",
                  pane=Blank(), runtime=Runtime(), now=time.time)
