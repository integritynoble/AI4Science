"""Tests for ai4science.wallet — local file mode + platform-linked mode.

The shared HTTP transport (wallet.http_request) is monkeypatched; no real
network calls. Platform mode hits the real endpoints
(/api/v1/pwm-token/balance, /api/v1/pwm-token/spend).
"""
from __future__ import annotations

import pytest

from ai4science import wallet

_TOKENS = ("AI4SCIENCE_PWM_TOKEN", "PWM_TOKEN", "PWM_ONBOARD_TOKEN")
_BASES = ("AI4SCIENCE_PWM_API", "PWM_BASE", "PWM_ONBOARD_BASE")


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_WALLET", str(tmp_path / "wallet.json"))
    for k in ("AI4SCIENCE_BILLING", *_TOKENS, *_BASES):
        monkeypatch.delenv(k, raising=False)
    yield


# ── mode detection ──

def test_local_mode_is_default():
    assert wallet.mode() == "local"


def test_token_auto_enables_platform(monkeypatch):
    monkeypatch.setenv("PWM_TOKEN", "pwm_k")
    assert wallet.mode() == "platform"


def test_explicit_local_overrides_token(monkeypatch):
    monkeypatch.setenv("PWM_TOKEN", "pwm_k")
    monkeypatch.setenv("AI4SCIENCE_BILLING", "local")
    assert wallet.mode() == "local"


# ── local file mode (back-compat) ──

def test_local_credit_debit_balance():
    assert wallet.balance() == 0.0
    assert wallet.credit(5) == 5.0
    assert wallet.debit(2) == 3.0
    assert wallet.balance() == 3.0


def test_local_debit_insufficient_is_valueerror():
    wallet.credit(1)
    with pytest.raises(wallet.InsufficientPWM):
        wallet.debit(10)
    with pytest.raises(ValueError):   # back-compat: InsufficientPWM is also a ValueError
        wallet.debit(10)


# ── platform-linked mode (mock the shared transport) ──

@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_BILLING", "platform")
    monkeypatch.setenv("PWM_TOKEN", "pwm_k")
    monkeypatch.setenv("PWM_BASE", "https://x")
    calls = []

    def fake_http(method, base, path, token, body=None):
        calls.append((method, base, path, token, body))
        assert token == "pwm_k"
        if path == wallet.BALANCE_PATH:
            return 200, {"balance": 1.5}
        if path == wallet.SPEND_PATH:
            amt = body["amount"]
            if amt > 1.5:
                return 402, {"detail": "insufficient", "balance_after": 1.5}
            return 200, {"success": True, "balance_after": round(1.5 - amt, 6)}
        return 404, {}

    monkeypatch.setattr(wallet, "http_request", fake_http)
    return calls


def test_platform_balance(platform):
    assert wallet.balance() == 1.5


def test_platform_debit_sends_real_spend_fields(platform):
    nb = wallet.debit(0.5, idempotency_key="op1", provider_wallet="0xabc",
                      purpose="ai4science:paper")
    assert nb == 1.0
    spend = next(c for c in platform if c[2] == wallet.SPEND_PATH)
    body = spend[4]
    assert body["amount"] == 0.5
    assert body["purpose"] == "ai4science:paper"
    assert body["provider_wallet"] == "0xabc"
    assert body["idempotency_key"] == "op1"


def test_platform_debit_insufficient_raises(platform):
    with pytest.raises(wallet.InsufficientPWM):
        wallet.debit(5.0, idempotency_key="op2", provider_wallet="0xabc")


def test_platform_debit_requires_idempotency_and_provider(platform):
    with pytest.raises(ValueError):
        wallet.debit(0.1, provider_wallet="0xabc")          # missing idempotency_key
    with pytest.raises(ValueError):
        wallet.debit(0.1, idempotency_key="op3")            # missing provider_wallet


def test_platform_credit_is_refused(platform):
    with pytest.raises(wallet.BillingError):
        wallet.credit(1.0)


def test_platform_requires_token(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_BILLING", "platform")    # no token
    with pytest.raises(wallet.BillingAuthError):
        wallet.balance()
