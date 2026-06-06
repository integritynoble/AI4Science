"""Tests for ai4science.wallet — local file mode + platform-linked mode.

The HTTP seam (wallet._request) is monkeypatched; no real network calls.
"""
from __future__ import annotations

import pytest

from ai4science import wallet


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_WALLET", str(tmp_path / "wallet.json"))
    for k in ("AI4SCIENCE_BILLING", "AI4SCIENCE_PWM_TOKEN", "AI4SCIENCE_PWM_API"):
        monkeypatch.delenv(k, raising=False)
    yield


# ── mode detection ──

def test_local_mode_is_default():
    assert wallet.mode() == "local"


def test_token_auto_enables_platform(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_PWM_TOKEN", "tok")
    assert wallet.mode() == "platform"


def test_explicit_local_overrides_token(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_PWM_TOKEN", "tok")
    monkeypatch.setenv("AI4SCIENCE_BILLING", "local")
    assert wallet.mode() == "local"


# ── local file mode (back-compat) ──

def test_local_credit_debit_balance():
    assert wallet.balance() == 0.0
    assert wallet.credit(5) == 5.0
    assert wallet.balance() == 5.0
    assert wallet.debit(2) == 3.0
    assert wallet.balance() == 3.0


def test_local_debit_insufficient_raises():
    wallet.credit(1)
    with pytest.raises(wallet.InsufficientPWM):
        wallet.debit(10)


# ── platform-linked mode (mock HTTP) ──

@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_BILLING", "platform")
    monkeypatch.setenv("AI4SCIENCE_PWM_TOKEN", "tok")
    calls = []

    def fake_request(method, path, token, body=None):
        calls.append((method, path, token, body))
        assert token == "tok"
        if path == "/balance":
            return 200, {"user": "u", "pwm": 1.5}
        if path == "/charge":
            amt = body["amount_pwm"]
            if amt > 1.5:
                return 402, {"charged": False, "error": "insufficient", "balance": 1.5, "needed": amt}
            return 200, {"charged": True, "amount_pwm": amt,
                         "new_balance": round(1.5 - amt, 6), "tx_id": "tx1"}
        return 404, {}

    monkeypatch.setattr(wallet, "_request", fake_request)
    return calls


def test_platform_balance(platform):
    assert wallet.balance() == 1.5


def test_platform_debit_success_sends_correct_charge(platform):
    nb = wallet.debit(0.5, idempotency_key="op1", provider_wallet="0xabc",
                      reason="deep_paper_review", meta={"model": "x"})
    assert nb == 1.0
    charge = next(c for c in platform if c[1] == "/charge")
    body = charge[3]
    assert body["idempotency_key"] == "op1"
    assert body["provider_wallet"] == "0xabc"
    assert body["amount_pwm"] == 0.5
    assert body["reason"] == "deep_paper_review"


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
    monkeypatch.setenv("AI4SCIENCE_BILLING", "platform")   # no token
    with pytest.raises(wallet.BillingAuthError):
        wallet.balance()
