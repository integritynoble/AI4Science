"""repl performs what console decides — and only repl touches the world.

The wiring is where the two halves can drift: a console that returns an action
repl does not handle is a command that silently does nothing, which is the
defect class this whole piece exists to remove.
"""
import pytest

from ai4science.harness import console, repl


def test_every_action_kind_console_can_return_is_handled_by_repl():
    """The drift guard. If console grows an action and repl does not learn it,
    the command does nothing and says nothing."""
    produced = {"answer", "say", "confirm", "create", "guide", "attach",
                "enter", "leave", "noop"}
    assert produced <= repl.HANDLED_ACTIONS


def test_deps_expose_every_key_route_reads():
    """route() indexes deps directly; a missing key is a KeyError inside the
    REPL loop, which is the one place nothing may raise."""
    d = repl._console_deps({})
    for key in ("resolve", "find_task", "suggest", "create", "guide",
                "session_of"):
        assert key in d, key
        assert callable(d[key])


def test_the_prompt_tracks_the_mode():
    state = {"mode": console.Mode(kind="agent", name="sarsi-worker")}
    assert repl._prompt_for(state) == "sarsi-worker ❯ "
    state["mode"] = console.Mode()
    assert repl._prompt_for(state) == "❯ "


def test_a_dep_that_raises_becomes_a_message_not_an_exception(monkeypatch):
    """Nothing in this path may drop the session the owner is standing in."""
    d = repl._console_deps({})
    monkeypatch.setattr(repl, "_find_task",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert isinstance(d["session_of"]("tsk_nope"), str)
