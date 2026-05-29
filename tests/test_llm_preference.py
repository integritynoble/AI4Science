"""Tests for #11 — user-vs-wallet source preference in routing."""
from __future__ import annotations

import pytest

from ai4science.llm import routing
from ai4science import user as user_cfg


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_USER_CONFIG", str(tmp_path / "user.json"))
    monkeypatch.setenv("AI4SCIENCE_KEYS", str(tmp_path / "keys.json"))

    class _P:
        def __init__(self, backend):
            self.provider_id = f"{backend}-wallet"
            self.wallet_address = "0x" + "cd" * 20
            self.price_multiplier = 0.5
            self.backend = backend
            self.status = "active"
    monkeypatch.setattr(routing, "_provider_for", lambda b: _P(b))


def test_default_user_first_when_logged_in_own():
    user_cfg.login_own("anthropic", "subscription")
    src, pid, wallet, mult = routing._select_source("anthropic")
    assert src == "user" and pid is None and wallet is None and mult == 0.0


def test_other_backend_falls_to_wallet():
    user_cfg.login_own("anthropic", "subscription")     # only own anthropic
    src, pid, _, mult = routing._select_source("openai")  # no own openai
    assert src == "wallet" and pid == "openai-wallet" and mult == 0.5


def test_no_login_uses_wallet():
    src, pid, _, _ = routing._select_source("anthropic")
    assert src == "wallet" and pid == "anthropic-wallet"


def test_wallet_preference_overrides_own():
    user_cfg.login_own("anthropic", "subscription")
    user_cfg.set_preference("wallet")
    src, pid, _, _ = routing._select_source("anthropic")
    assert src == "wallet" and pid == "anthropic-wallet"


def test_user_source_is_zero_pwm_in_route(monkeypatch):
    user_cfg.login_own("anthropic", "subscription")
    monkeypatch.setattr(routing, "backend_available", lambda b: b == "anthropic")
    r = routing.resolve("orchestration")     # first reachable = anthropic
    assert r.source == "user"
    assert r.price_multiplier == 0.0         # billed to the user's own account
