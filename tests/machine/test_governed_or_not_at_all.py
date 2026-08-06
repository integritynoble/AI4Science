"""`govern=True` is a request that must be honoured or refused, never dropped.

    if govern:
        try:
            wire(cwd, ceiling=ceiling, writable=writable)
        except Exception:
            pass
    rc, out, err = run(["tmux", "new-session", ...])

If wiring the PreToolUse hook throws for any reason — a read-only `.claude`,
a full disk, a `TypeError` because a caller passed the wrong `wire` — the
session starts anyway. Ungoverned: no ceiling, no gates, nothing asking. And
the caller is handed `ok: True` and a session name, so every layer above
believes it is governed. For a `claude-code` session that hook is the **only**
boundary in force, which makes this the widest silent failure in the file.

The rule is the one `start_session` already learned the hard way about panes:

    **A session that is not what was asked for is not started.**

Refusing costs a run. Starting ungoverned costs the boundary, and does it
quietly — the owner finds out by reading a transcript afterwards, if ever.

This is the same defect as the one caught live in `release_session`: `except
Exception` wrapped around a call whose failure mode is *"the caller passed the
wrong object"*, turning a programming error into silent wrong behaviour.
"""
import pytest

from ai4science.harness.agents.machine import sessions


def _tmux(started):
    def run(cmd):
        if "new-session" in cmd:
            started.append(cmd)
            return (0, "", "")
        if "list-panes" in cmd:
            return (0, "4242", "")
        return (0, "", "")
    return run


def _boom(cwd, **kw):
    raise OSError("read-only file system: .claude/settings.json")


def _wrong_signature(cwd):          # a caller that forgot the keywords
    return "/p/.claude/settings.json"


# ── it refuses rather than starting ungoverned ────────────────────────

def test_a_session_that_cannot_be_governed_is_not_started():
    started = []
    got = sessions.start_session("s", "/p", govern=True, ceiling="A1",
                                 wire=_boom, run=_tmux(started),
                                 register=lambda **kw: {"name": "s"})
    assert got["ok"] is False
    assert started == [], "an ungoverned session was started anyway"


def test_and_the_reason_says_it_was_the_governance():
    got = sessions.start_session("s", "/p", govern=True, ceiling="A1",
                                 wire=_boom, run=_tmux([]),
                                 register=lambda **kw: {"name": "s"})
    reason = got["reason"].lower()
    assert "govern" in reason
    assert "read-only file system" in reason      # the cause, not just the fact


def test_a_caller_error_is_refused_the_same_way():
    """`TypeError` here means the wrong `wire` was passed. Swallowing it starts
    an ungoverned session because of a programming mistake — the exact shape
    that left a live terminal running after a task verified."""
    started = []
    got = sessions.start_session("s", "/p", govern=True, ceiling="A1",
                                 wire=_wrong_signature, run=_tmux(started),
                                 register=lambda **kw: {"name": "s"})
    assert got["ok"] is False
    assert started == []


# ── and everything else is unchanged ──────────────────────────────────

def test_a_governed_session_that_wires_cleanly_still_starts():
    started = []
    got = sessions.start_session("s", "/p", govern=True, ceiling="A1",
                                 wire=lambda cwd, **kw: None,
                                 run=_tmux(started),
                                 register=lambda **kw: {"name": "s"})
    assert got["ok"] is True
    assert started, "the happy path must still start"


def test_an_ungoverned_session_is_not_affected():
    """Nothing was asked for, so nothing was dropped. `govern=False` is a
    deliberate choice a caller makes, not a failure."""
    started = []
    got = sessions.start_session("s", "/p", govern=False,
                                 run=_tmux(started),
                                 register=lambda **kw: {"name": "s"})
    assert got["ok"] is True
    assert started


def test_the_pane_check_still_applies_to_a_governed_start():
    """Both refusals hold at once: wired, and actually running."""
    def no_pane(cmd):
        return (0, "", "") if "new-session" in cmd else (1, "", "gone")
    got = sessions.start_session("s", "/p", govern=True, ceiling="A1",
                                 wire=lambda cwd, **kw: None, run=no_pane,
                                 register=lambda **kw: {"name": "s"})
    assert got["ok"] is False
    assert "did not stay up" in got["reason"]
