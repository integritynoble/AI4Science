"""Token → USD → PWM pricing (design points 9 + 14).

Official per-token list prices (USD per 1M tokens) by model. A provider bills
at its `price_multiplier` (0.5 = half, for subscriptions per point 9; Gemini at
its comparegpt rate). 1 PWM = $5 (point 14 — the peg is just a denomination;
real value comes from the subscription↔official spread, a platform fee, and a
capped supply, not from setting the peg high).

PRICES_USD_PER_M are approximate launch defaults — EDIT them as official rates
change, or override per-model via the registry later.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

# 1 PWM in USD (reference peg). Override with AI4SCIENCE_PWM_USD.
PWM_USD = float(os.environ.get("AI4SCIENCE_PWM_USD", "5.0"))

# (input, output) USD per 1,000,000 tokens — official list prices (approx).
PRICES_USD_PER_M: Dict[str, Tuple[float, float]] = {
    # Anthropic
    "claude-fable-5":         (15.0, 75.0),   # Opus-tier pricing until official list price lands
    "claude-opus-4-8":        (15.0, 75.0),
    "claude-sonnet-4-6":      (3.0, 15.0),
    "claude-haiku-4-5":       (0.80, 4.0),
    # OpenAI
    "gpt-5.5":                (1.25, 10.0),
    "gpt-5.5-nano":           (0.05, 0.40),
    # Gemini (comparegpt basis)
    "gemini-3.5-flash":       (0.30, 2.50),
    "gemini-3.1-pro-preview": (1.25, 10.0),
    # DeepSeek / Qwen via Vertex (Model Garden / MaaS — approximate)
    "deepseek-ai/deepseek-r1-0528-maas":          (1.35, 5.40),
    "qwen/qwen3-235b-a22b-instruct-2507-maas":    (1.0, 3.0),
}
DEFAULT_PRICE: Tuple[float, float] = (2.0, 10.0)   # unknown model fallback

#: Cache rates, as MULTIPLES of the input price rather than looked-up prices —
#: they track the input rate across models, and a second table would drift from
#: the first. A cache READ is an order of magnitude cheaper than fresh input;
#: a cache WRITE carries a premium because it is written once and read many
#: times.
#:
#: This is the whole correctness of pricing a Claude Code session: one live
#: session on grace read 1,006 fresh tokens against 8,201,359 cached, so
#: charging cache at the input rate would inflate its value — and any fee
#: computed from it — by orders of magnitude. `spend` already keeps the two
#: apart and says why: both are "input" and they are nowhere near the same cost.
CACHE_READ = 0.1
CACHE_WRITE = 1.25


def model_price(model: str) -> Tuple[float, float]:
    return PRICES_USD_PER_M.get(model, DEFAULT_PRICE)


def usd_to_pwm(usd: float) -> float:
    return usd / PWM_USD if PWM_USD else 0.0


def price_call(model: str, usage: Dict[str, Optional[int]],
               price_multiplier: float = 1.0) -> Dict[str, float]:
    """Cost of one call. usage may have input/output (exact) or only total
    (e.g. codex) — total is priced at the blended (input+output)/2 rate.

    Returns {usd_official, usd_billed, pwm} (billed = official × multiplier)."""
    pin, pout = model_price(model)
    inp = usage.get("input")
    out = usage.get("output")
    total = usage.get("total")
    if inp is not None or out is not None:
        usd = (inp or 0) / 1e6 * pin + (out or 0) / 1e6 * pout
    elif total is not None:
        usd = total / 1e6 * ((pin + pout) / 2.0)
    else:
        usd = 0.0
    billed = usd * price_multiplier
    return {
        "usd_official": round(usd, 6),
        "usd_billed": round(billed, 6),
        "pwm": round(usd_to_pwm(billed), 6),
    }


def price_session(model: str, *, input: Optional[int] = 0,
                  output: Optional[int] = 0, cached: Optional[int] = 0,
                  cache_write: Optional[int] = 0) -> Dict[str, Any]:
    """What a whole session's tokens are worth, cache-aware.

    `price_call` takes input/output/total and has no cache rate, which is fine
    for the calls this harness makes itself and wrong for a Claude Code
    session, where the cached tokens dominate.

    `known_model` is returned rather than swallowed: a price taken from the
    fallback is a guess, and a fee built on a guess should be able to say so.
    """
    pin, pout = model_price(model)
    usd = ((input or 0) / 1e6 * pin
           + (output or 0) / 1e6 * pout
           + (cached or 0) / 1e6 * pin * CACHE_READ
           + (cache_write or 0) / 1e6 * pin * CACHE_WRITE)
    return {"usd": round(usd, 6), "pwm": round(usd_to_pwm(usd), 6),
            "known_model": model in PRICES_USD_PER_M}
