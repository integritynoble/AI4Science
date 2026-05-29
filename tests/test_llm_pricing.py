"""Tests for token→USD→PWM pricing + the consumption ledger (points 6, 9, 14)."""
from __future__ import annotations

from ai4science.llm import pricing, ledger


def test_exact_input_output_pricing():
    # opus 4.8 = $15/M in, $75/M out. 1M in + 1M out = $90 official.
    c = pricing.price_call("claude-opus-4-8",
                           {"input": 1_000_000, "output": 1_000_000}, price_multiplier=1.0)
    assert round(c["usd_official"], 2) == 90.0
    assert round(c["pwm"], 2) == round(90.0 / pricing.PWM_USD, 2)


def test_half_price_multiplier():
    c = pricing.price_call("claude-opus-4-8",
                           {"input": 1_000_000, "output": 0}, price_multiplier=0.5)
    # official input cost = $15; billed at half = $7.50
    assert round(c["usd_official"], 2) == 15.0
    assert round(c["usd_billed"], 2) == 7.5


def test_total_only_uses_blended_rate():
    # gpt-5.5-nano = (0.05, 0.40) → blended 0.225 /M. 1M total → $0.225.
    c = pricing.price_call("gpt-5.5-nano", {"total": 1_000_000}, price_multiplier=1.0)
    assert round(c["usd_official"], 4) == 0.225


def test_unknown_model_uses_default():
    c = pricing.price_call("mystery-model", {"input": 1_000_000, "output": 0})
    assert c["usd_official"] == 2.0      # DEFAULT_PRICE input = $2/M


def test_ledger_record_and_summary(tmp_path):
    p = tmp_path / "ledger.jsonl"
    ledger.record(agent="checking", backend="openai", model="gpt-5.5",
                  wallet="0xWALLET4", usage={"total": 1000},
                  cost={"usd_official": 0.01, "usd_billed": 0.005, "pwm": 0.001}, path=p)
    ledger.record(agent="fast", backend="gemini", model="gemini-3.5-flash",
                  wallet="0xWALLET3", usage={"input": 10, "output": 5},
                  cost={"usd_official": 0.002, "usd_billed": 0.002, "pwm": 0.0004}, path=p)
    s = ledger.summary(path=p)
    assert s["calls"] == 2
    assert "0xWALLET4" in s["per_wallet"] and "0xWALLET3" in s["per_wallet"]
    assert round(s["total_pwm"], 4) == 0.0014
