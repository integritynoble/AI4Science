"""`run` may not report a session it did not get.

Live on grace: `sarsi run` printed *"tsk_c8bcc7d118 — planning in session
sarsi-worker-d118"*, and there was no tmux server at all. A minute later
`attention` caught it as a dead-session, which is the reporting layer doing its
job — but by then the record already said a session was steering the task, and
the only reason anyone knew otherwise is that someone went and looked.

The cause is that `tmux new-session -d … <cmd>` answers a narrower question than
the one being asked. Return code 0 means *tmux accepted the command*, not *the
command is running*. A binary that is missing from `PATH`, or that exits on its
first line, leaves rc 0 and no session behind it. `start_session` then failed to
read a pane pid, set `pid = None`, and returned `ok: True` regardless.

So the rule this file holds is the one the rest of the system already follows:

  **a start is confirmed by the pane, not by the launcher's exit code.**

No pane means no session, and `ok: False` with the reason — which for the case
that actually happened is a command that is not on this machine, and the message
should say so rather than leaving the owner to discover an empty tmux.
"""
import pytest

from ai4science.harness.agents.machine import sessions


def _tmux(*, accepts=True, panes=""):
    """A fake tmux. `accepts` is what `new-session` returns; `panes` is what
    `list-panes` finds afterwards — the two are independent, which is the whole
    point."""
    calls = []

    def run(cmd):
        calls.append(cmd)
        if "new-session" in cmd:
            return (0, "", "") if accepts else (1, "", "no server")
        if "list-panes" in cmd:
            return (0, panes, "") if panes else (1, "", "can't find session")
        return (0, "", "")

    run.calls = calls
    return run


def test_a_session_with_a_pane_is_started():
    got = sessions.start_session("s1", "/tmp", run=_tmux(panes="4242"),
                                 register=lambda **kw: {"name": "s1"})
    assert got["ok"] is True
    assert got["pid"] == 4242


def test_tmux_refusing_outright_is_already_reported():
    got = sessions.start_session("s1", "/tmp", run=_tmux(accepts=False))
    assert got["ok"] is False


def test_accepted_but_no_pane_is_not_a_started_session():
    """The live case. tmux took the command and the command was gone before
    the next call — rc 0, nothing running."""
    got = sessions.start_session("s1", "/tmp", run=_tmux(accepts=True, panes=""))
    assert got["ok"] is False


def test_and_the_reason_says_the_command_did_not_stay_up():
    got = sessions.start_session("s1", "/tmp", run=_tmux(accepts=True, panes=""),
                                 claude_bin="claude")
    assert "claude" in got["reason"]
    assert "exit" in got["reason"].lower() or "not stay" in got["reason"].lower()


def test_the_reason_points_at_the_likeliest_cause():
    """It was `PATH` on the live machine — `claude` is in `~/.local/bin`, which
    a non-login shell does not have. An owner reading this should not have to
    rediscover that."""
    got = sessions.start_session("s1", "/tmp", run=_tmux(accepts=True, panes=""))
    assert "PATH" in got["reason"]


def test_a_failed_start_registers_nothing():
    """A supervisor record for a session that is not there is exactly what made
    the task claim it was being steered."""
    registered = []
    sessions.start_session("s1", "/tmp", run=_tmux(accepts=True, panes=""),
                           register=lambda **kw: registered.append(kw))
    assert registered == []
