"""Tests for the compute marketplace: pricing + provider selection (#12/#13)."""
from __future__ import annotations

import pytest

from ai4science.compute import pricing
from ai4science.compute.registry import ComputeProvider


def test_job_cost_hours_usd_pwm(monkeypatch):
    # 1800s = 0.5h × $2/hr = $1 → 0.2 PWM at $5/PWM
    monkeypatch.setattr("ai4science.llm.pricing.PWM_USD", 5.0)
    c = pricing.job_cost(1800, 2.0)
    assert c["hours"] == 0.5
    assert c["usd"] == 1.0
    assert c["pwm"] == 0.2


def test_job_cost_zero_when_no_time_or_rate():
    assert pricing.job_cost(None, 2.0)["usd"] == 0.0
    assert pricing.job_cost(3600, 0.0)["usd"] == 0.0


def _provs(monkeypatch, providers, eligible_ids):
    monkeypatch.setattr("ai4science.compute.registry.load_registry", lambda: providers)
    monkeypatch.setattr("ai4science.staking.is_eligible",
                        lambda pid, *a, **k: pid in eligible_ids)


def _p(pid, kind="gpu", price=1.0, status="active"):
    return ComputeProvider(provider_id=pid, wallet_address="0x" + "ab" * 20,
                           endpoint_path="/tmp/x", kind=kind,
                           price_usd_per_hour=price, status=status)


def test_select_cheapest_eligible_gpu(monkeypatch):
    provs = [_p("gpu-a", price=3.0), _p("gpu-b", price=1.0), _p("cpu-c", kind="cpu", price=0.5)]
    _provs(monkeypatch, provs, {"gpu-a", "gpu-b", "cpu-c"})
    chosen = pricing.select("gpu")
    assert chosen.provider_id == "gpu-b"          # cheapest GPU


def test_select_skips_ineligible(monkeypatch):
    provs = [_p("gpu-cheap", price=0.5), _p("gpu-dear", price=2.0)]
    _provs(monkeypatch, provs, {"gpu-dear"})      # cheap one not staked-eligible
    chosen = pricing.select("gpu")
    assert chosen.provider_id == "gpu-dear"


def test_select_none_when_no_eligible(monkeypatch):
    _provs(monkeypatch, [_p("gpu-a")], set())
    assert pricing.select("gpu") is None


def test_kind_validation():
    with pytest.raises(ValueError):
        _p("bad", kind="quantum")
