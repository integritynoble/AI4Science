"""Tests for provider stake / collateral (the no-burn hold-reason)."""
from __future__ import annotations

import pytest

from ai4science import staking


def test_stake_unstake_balance(tmp_path, monkeypatch):
    p = tmp_path / "stakes.jsonl"
    monkeypatch.setattr(staking, "provider_wallet", lambda pid: "0xWALLET")
    staking.stake("prov-a", 120, path=p)
    staking.stake("prov-a", 30, path=p)
    assert staking.staked("prov-a", path=p) == 150
    staking.unstake("prov-a", 50, path=p)
    assert staking.staked("prov-a", path=p) == 100


def test_cannot_unstake_more_than_balance(tmp_path, monkeypatch):
    p = tmp_path / "stakes.jsonl"
    monkeypatch.setattr(staking, "provider_wallet", lambda pid: "0xW")
    staking.stake("prov-b", 10, path=p)
    with pytest.raises(ValueError):
        staking.unstake("prov-b", 25, path=p)


def test_slash_never_below_zero(tmp_path, monkeypatch):
    p = tmp_path / "stakes.jsonl"
    monkeypatch.setattr(staking, "provider_wallet", lambda pid: "0xW")
    staking.stake("prov-c", 40, path=p)
    staking.slash("prov-c", 100, "judge: silent_failure", path=p)   # clamped to 40
    assert staking.staked("prov-c", path=p) == 0
    assert staking.slashed_total("prov-c", path=p) == 40


def test_eligibility_founder_exempt(tmp_path, monkeypatch):
    p = tmp_path / "stakes.jsonl"
    monkeypatch.setattr(staking, "provider_wallet", lambda pid: "0xW")
    monkeypatch.setattr(staking, "provider_tier", lambda pid: "founder")
    # founder eligible with zero stake
    assert staking.is_eligible("founder-x", path=p) is True


def test_eligibility_community_needs_min(tmp_path, monkeypatch):
    p = tmp_path / "stakes.jsonl"
    monkeypatch.setattr(staking, "provider_wallet", lambda pid: "0xW")
    monkeypatch.setattr(staking, "provider_tier", lambda pid: "open")
    monkeypatch.setattr(staking, "MIN_STAKE_PWM", 100)
    assert staking.is_eligible("open-y", path=p) is False     # 0 < 100
    staking.stake("open-y", 100, path=p)
    assert staking.is_eligible("open-y", path=p) is True      # 100 >= 100
