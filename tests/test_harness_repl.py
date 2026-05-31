"""Tests for the native-harness REPL (non-interactive parts).

We can't test the full input() loop in CI, so we test the helpers:
  - _pick_brand() selects a sensible default or honours overrides
  - run_common_repl() processes a multi-turn scripted session via stdin patching
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from ai4science.harness.repl import _pick_brand, run_common_repl
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done
from ai4science.llm import routing


# ─── _pick_brand ────────────────────────────────────────────────────────


def test_pick_brand_explicit_both():
    b, m = _pick_brand("openai", "gpt-5.5")
    assert b == "openai" and m == "gpt-5.5"


def test_pick_brand_explicit_backend_only():
    # "anthropic" is in the orchestration chain; we should get a model from there.
    b, m = _pick_brand("anthropic", None)
    assert b == "anthropic"
    assert m  # some model string


def test_pick_brand_auto_fallback(monkeypatch):
    """When no backend is reachable, falls back to anthropic/claude-opus-4-8."""
    monkeypatch.setattr(routing, "backend_available", lambda _: False)
    b, m = _pick_brand(None, None)
    assert b == "anthropic"
    assert m == "claude-opus-4-8"


def test_pick_brand_auto_picks_first_reachable(monkeypatch):
    """Auto-detect returns the first reachable entry in the orchestration chain."""
    first_backend = routing.AGENT_CHAINS["orchestration"][0][0]
    monkeypatch.setattr(routing, "backend_available",
                        lambda b: b == first_backend)
    b, m = _pick_brand(None, None)
    assert b == first_backend


# ─── run_common_repl (scripted via stdin) ───────────────────────────────


def test_repl_runs_turn_and_streams_text(tmp_path, monkeypatch, capsys):
    """Feed one user line and /exit; session should stream stub output."""
    script = [[TextDelta("hi there"), Done("end")]]
    stub = StubAdapter(script)

    # Patch adapter_for so the REPL gets our stub.
    import ai4science.harness.repl as repl_mod
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: stub)
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    # Make backend_available return True for "anthropic" so _pick_brand is happy.
    monkeypatch.setattr(routing, "backend_available", lambda b: b == "anthropic")

    inputs = iter(["say hi", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_common_repl(tmp_path, read_only=True, auto_yes=False,
                    backend="anthropic", model="stub")

    out = capsys.readouterr().out
    assert "hi there" in out


def test_repl_model_switch(tmp_path, monkeypatch, capsys):
    """/model openai switches the session brand."""
    script = [[TextDelta("hello"), Done("end")]]
    stub = StubAdapter(script)

    import ai4science.harness.repl as repl_mod
    created_backends = []

    def _fake_adapter_for(b):
        created_backends.append(b)
        return stub

    monkeypatch.setattr(repl_mod, "adapter_for", _fake_adapter_for)
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)

    inputs = iter(["/model openai gpt-5.5", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_common_repl(tmp_path, read_only=True, auto_yes=False,
                    backend="anthropic", model="stub")

    out = capsys.readouterr().out
    assert "openai" in out
    # adapter_for was called at least once for the switch
    assert "openai" in created_backends


def test_repl_exit_slash_stops_loop(tmp_path, monkeypatch, capsys):
    """/exit stops the loop without making any LLM turn calls."""
    script = []  # empty — no turns should be driven
    stub = StubAdapter(script)

    import ai4science.harness.repl as repl_mod
    turn_calls = []

    # Wrap run_turn to record if it's ever called.
    original_run_turn = None

    def _fake_adapter_for(b):
        return stub

    monkeypatch.setattr(repl_mod, "adapter_for", _fake_adapter_for)
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)

    inputs = iter(["/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    run_common_repl(tmp_path, read_only=True, backend="anthropic", model="stub")
    out = capsys.readouterr().out
    # Adapter was called for session setup but no turns were driven.
    assert "bye" in out
    assert stub._i == 0   # StubAdapter index: no turns consumed


def test_run_common_repl_wires_per_edit_confirm(tmp_path, monkeypatch):
    """run_common_repl MUST pass a confirm handler, else the permission gate
    blocks every mutation in default (non-auto-yes, non-read-only) mode."""
    import ai4science.harness.repl as repl_mod
    from ai4science.harness.adapters.stub import StubAdapter

    captured = {}
    real_cls = repl_mod.AgentSession

    def _capture(**kwargs):
        captured.update(kwargs)
        return real_cls(**kwargs)

    monkeypatch.setattr(repl_mod, "AgentSession", _capture)
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: StubAdapter([[]]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)

    def _eof(*a, **k):
        raise EOFError()

    monkeypatch.setattr("builtins.input", _eof)

    repl_mod.run_common_repl(tmp_path, backend="anthropic", model="stub")
    assert captured.get("confirm") is not None
