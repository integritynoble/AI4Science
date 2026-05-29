"""Tests for onboarding: user config + local hot-key wallet (points 4–6)."""
from __future__ import annotations

import pytest

from ai4science import user as user_cfg
from ai4science import wallet as local_wallet


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_USER_CONFIG", str(tmp_path / "user.json"))
    monkeypatch.setenv("AI4SCIENCE_KEYS", str(tmp_path / "keys.json"))
    monkeypatch.setenv("AI4SCIENCE_WALLET", str(tmp_path / "wallet.json"))


def test_login_own_subscription():
    cfg = user_cfg.login_own("anthropic", "subscription")
    assert cfg["power"] == "own" and cfg["provider"] == "anthropic"
    assert user_cfg.preferred_backend() == "anthropic"
    assert user_cfg.get_api_key("anthropic") is None


def test_login_own_api_key_is_stored_separately():
    user_cfg.login_own("openai", "api_key", api_key="sk-test-123")
    assert user_cfg.get_api_key("openai") == "sk-test-123"
    assert user_cfg.load()["api_key_set"] is True


def test_login_own_rejects_unknown_provider():
    with pytest.raises(ValueError):
        user_cfg.login_own("not-a-provider", "subscription")


def test_login_wallet_and_logout():
    user_cfg.login_wallet()
    assert user_cfg.load()["power"] == "wallet"
    assert user_cfg.preferred_backend() is None     # wallet mode → no own backend
    user_cfg.logout()
    assert user_cfg.load() == {}


def test_wallet_credit_debit():
    assert local_wallet.balance() == 0.0
    assert local_wallet.address().startswith("0x")
    local_wallet.credit(50)
    assert local_wallet.balance() == 50
    local_wallet.debit(20)
    assert local_wallet.balance() == 30
    with pytest.raises(ValueError):
        local_wallet.debit(1000)                    # insufficient


def test_wallet_address_is_stable():
    a1 = local_wallet.address()
    a2 = local_wallet.address()
    assert a1 == a2 and len(a1) == 42               # 0x + 40 hex
