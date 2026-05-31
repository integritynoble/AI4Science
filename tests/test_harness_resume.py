"""Task 4 — --continue/--resume for common mode.

Tests that run_common_repl accepts a resume_history kwarg and seeds the
AgentSession with it before the main REPL loop starts.
"""
from __future__ import annotations

from pathlib import Path

from ai4science.harness import repl as repl_mod
from ai4science.harness.events import Message


def test_run_common_repl_seeds_resume_history(tmp_path, monkeypatch):
    from ai4science.harness.adapters.stub import StubAdapter

    captured = {}
    real = repl_mod.AgentSession

    def _capture(**kwargs):
        s = real(**kwargs)
        captured["session"] = s
        return s

    monkeypatch.setattr(repl_mod, "AgentSession", _capture)
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: StubAdapter([[]]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)

    def _eof(*a, **k):
        raise EOFError()

    monkeypatch.setattr("builtins.input", _eof)

    prior = [
        Message(role="user", content="earlier"),
        Message(role="assistant", content="ok"),
    ]
    repl_mod.run_common_repl(
        tmp_path, backend="anthropic", model="stub",
        resume_history=prior,
    )
    assert [m.content for m in captured["session"].history] == ["earlier", "ok"]
