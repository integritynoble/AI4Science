"""Tests for agent → LLM routing with fallback (design point 10)."""
from __future__ import annotations

from ai4science.llm import routing


def _stub_providers(monkeypatch):
    """Make _provider_for return a fake provider so wallet resolution works."""
    class _P:
        def __init__(self, backend):
            self.provider_id = f"{backend}-prov"
            self.wallet_address = "0x" + "ab" * 20
    monkeypatch.setattr(routing, "_provider_for", lambda b: _P(b))


def test_orchestration_first_choice_is_opus(monkeypatch):
    _stub_providers(monkeypatch)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)
    r = routing.resolve("orchestration")
    assert r.backend == "anthropic"
    assert r.model == "claude-opus-4-8"
    assert r.is_fallback is False
    assert r.wallet.startswith("0x")


def test_checking_prefers_gpt55(monkeypatch):
    _stub_providers(monkeypatch)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)
    r = routing.resolve("checking")
    assert (r.backend, r.model) == ("openai", "gpt-5.5")


def test_fast_prefers_gemini(monkeypatch):
    _stub_providers(monkeypatch)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)
    r = routing.resolve("fast")
    assert r.backend == "gemini"


def test_orchestration_falls_back_when_anthropic_down(monkeypatch):
    """Opus unavailable → orchestration routes to the next reachable (openai)."""
    _stub_providers(monkeypatch)
    monkeypatch.setattr(routing, "backend_available", lambda b: b != "anthropic")
    r = routing.resolve("orchestration")
    assert r.backend == "openai"
    assert r.model == "gpt-5.5"
    assert r.is_fallback is True


def test_resolve_none_when_all_down(monkeypatch):
    _stub_providers(monkeypatch)
    monkeypatch.setattr(routing, "backend_available", lambda b: False)
    assert routing.resolve("orchestration") is None


def test_unknown_agent_returns_none():
    assert routing.resolve("bogus-agent") is None
