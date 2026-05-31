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


def test_mode_toggle_preserves_history(tmp_path, monkeypatch):
    """/readonly mid-session must toggle the gate IN PLACE, not wipe history."""
    import ai4science.harness.repl as repl_mod
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.events import TextDelta, Done
    from ai4science.llm import routing

    captured = {}
    real = repl_mod.AgentSession

    def _cap(**kw):
        s = real(**kw)
        captured["s"] = s
        return s

    monkeypatch.setattr(repl_mod, "AgentSession", _cap)
    monkeypatch.setattr(repl_mod, "adapter_for",
                        lambda b: StubAdapter([[TextDelta("hi"), Done("end")]]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)
    monkeypatch.setattr("ai4science.harness.persistence.save", lambda *a, **k: None)

    inputs = iter(["say hi", "/readonly", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    repl_mod.run_common_repl(tmp_path, backend="anthropic", model="stub")
    s = captured["s"]
    # the real "say hi" turn happened before /readonly; history must survive
    assert any(m.role == "user" and m.content == "say hi" for m in s.history)
    # and the gate is now read-only (toggle took effect in place)
    assert s.gate.read_only is True
