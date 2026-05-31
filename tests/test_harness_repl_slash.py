from __future__ import annotations

from ai4science.harness.repl import _dispatch_slash


def test_help_lists_commands():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    handled, msg = _dispatch_slash("/help", state)
    assert handled and "/model" in msg and "/clear" in msg


def test_readonly_and_yes_toggle_state():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    _dispatch_slash("/readonly", state)
    assert state["read_only"] is True
    _dispatch_slash("/yes", state)
    assert state["auto_yes"] is True
    _dispatch_slash("/default", state)
    assert state["read_only"] is False and state["auto_yes"] is False


def test_exit_sets_flag():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    handled, _ = _dispatch_slash("/exit", state)
    assert handled and state["exit"] is True


def test_unknown_slash_not_handled():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    handled, _ = _dispatch_slash("/bogus", state)
    assert handled is False
