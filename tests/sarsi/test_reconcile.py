"""Reconciling the record against the machine, on entry.

Sessions outlive the process that started them. The task record says which
terminal it believes in, and that belief was last checked when it was written —
so entering a worker reported state that was true at some point in the past and
presented it as now.

Two disagreements, and they point opposite ways:

  * **a record with no terminal** — the task looks alive on the board and
    nothing is running;
  * **a terminal with no record** — something is running that no task claims,
    still holding whatever it was granted. The more dangerous of the two,
    because the board shows nothing at all.

And one rule that matters more than either: **"tmux says no such session" and
"tmux could not be asked" are different answers.** If the server is down, every
record looks dead — reporting "3 terminals are gone" would be alarming and
wrong. Unknown is reported as unknown.
"""
import pytest

from ai4science.harness.agents.sarsi import (entry, plan as pl, registry as reg,
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

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.start(config, agent, t)


def _running(config, agent, goal="finish the export"):
    return ses.assign(config, agent, _task(config, agent, goal),
                      runtime=FakeRuntime())


# ── agreement ─────────────────────────────────────────────────────────

def test_a_record_backed_by_a_live_terminal_agrees(config, agent):
    t = _running(config, agent)
    out = entry.reconcile(config, agent, live=lambda: {t.session["name"]})
    assert out.running == 1
    assert out.missing == [] and out.unclaimed == []


def test_a_worker_with_nothing_running_agrees_too(config, agent):
    _task(config, agent)
    out = entry.reconcile(config, agent, live=lambda: set())
    assert out.running == 0 and not out.disagrees


# ── a record with no terminal ─────────────────────────────────────────

def test_a_record_pointing_at_a_gone_terminal_is_named(config, agent):
    t = _running(config, agent)
    out = entry.reconcile(config, agent, live=lambda: set())
    assert out.missing == [t.id]
    assert out.disagrees


def test_it_says_so_in_words(config, agent):
    _running(config, agent)
    out = entry.reconcile(config, agent, live=lambda: set())
    assert "gone" in out.summary or "not there" in out.summary


# ── a terminal with no record ─────────────────────────────────────────

def test_a_live_terminal_no_task_claims_is_named(config, agent):
    """The more dangerous direction: the board shows nothing at all."""
    out = entry.reconcile(config, agent, live=lambda: {"work-9zz9"})
    assert out.unclaimed == ["work-9zz9"]
    assert out.disagrees


def test_another_agents_session_is_not_this_agents_problem(config, agent):
    out = entry.reconcile(config, agent, live=lambda: {"social-1234"})
    assert out.unclaimed == []


def test_a_session_belonging_to_an_archived_task_still_counts_as_claimed(config, agent):
    """Archiving stops the session; if one survived, it is missing-record only
    in the sense that the task is closed — but it is not UNCLAIMED, and calling
    it that would send the owner looking for a task that is right there."""
    t = _running(config, agent)
    name = t.session["name"]
    tsk.archive(config, agent, t)
    out = entry.reconcile(config, agent, live=lambda: {name})
    assert out.unclaimed == []


# ── unknown is not the same as gone ───────────────────────────────────

def test_tmux_being_unreachable_is_reported_as_unknown(config, agent):
    """If the server is down every record looks dead. Reporting '3 terminals
    are gone' would be alarming and wrong."""
    def broken():
        raise OSError("tmux server not running")

    t = _running(config, agent)
    out = entry.reconcile(config, agent, live=broken)
    assert out.unknown is True
    assert out.missing == [] and out.unclaimed == []
    assert "could not" in out.summary.lower() or "unknown" in out.summary.lower()


def test_unknown_does_not_read_as_agreement(config, agent):
    def broken():
        raise OSError("nope")

    _running(config, agent)
    assert entry.reconcile(config, agent, live=broken).summary != "1 running"


# ── it shows up on entry ──────────────────────────────────────────────

def test_entering_reports_the_disagreement(config, agent):
    t = _running(config, agent)
    out = entry.enter(config, agent, surface="cli", live=lambda: set())
    assert "gone" in out or "not there" in out


def test_entering_says_nothing_extra_when_the_record_agrees(config, agent):
    t = _running(config, agent)
    out = entry.enter(config, agent, surface="cli",
                      live=lambda: {t.session["name"]})
    assert "gone" not in out


def test_entering_an_empty_worker_still_asks_what_you_want(config, agent):
    """Reconciliation must not displace the question."""
    out = entry.enter(config, agent, surface="cli", live=lambda: set())
    assert "?" in out
