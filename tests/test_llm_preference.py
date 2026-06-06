"""Tests for routing source selection.

Policy: AI4Science has NO free 'bring-your-own-API-key' path — every turn is
billed in PWM to a wallet-bound provider. Supplying an LLM (key or subscription)
means registering a provider with a wallet, which then earns PWM.
"""
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


def test_own_login_still_billed_to_wallet():
    # Even after logging in your own creds, there is NO free path: usage routes
    # to the wallet-bound provider and is billed in PWM.
    user_cfg.login_own("anthropic", "subscription")
    src, pid, wallet, mult = routing._select_source("anthropic")
    assert src == "wallet" and pid == "anthropic-wallet" and mult == 0.5
    assert wallet and wallet != ""


def test_no_login_uses_wallet():
    src, pid, _, _ = routing._select_source("anthropic")
    assert src == "wallet" and pid == "anthropic-wallet"


def test_wallet_preference_uses_wallet():
    user_cfg.login_own("anthropic", "subscription")
    user_cfg.set_preference("wallet")
    src, pid, _, _ = routing._select_source("anthropic")
    assert src == "wallet" and pid == "anthropic-wallet"


def test_no_provider_returns_none(monkeypatch):
    # No wallet-bound provider for a backend → 'none' (usage blocked), never free.
    monkeypatch.setattr(routing, "_provider_for", lambda b: None)
    src, pid, wallet, mult = routing._select_source("anthropic")
    assert src == "none" and pid is None and wallet is None and mult == 0.0


def test_route_is_billed_in_pwm(monkeypatch):
    user_cfg.login_own("anthropic", "subscription")
    monkeypatch.setattr(routing, "backend_available", lambda b: b == "anthropic")
    r = routing.resolve("orchestration")     # first reachable = anthropic
    assert r.source == "wallet"
    assert r.price_multiplier == 0.5         # billed in PWM to the provider wallet
    assert r.wallet
