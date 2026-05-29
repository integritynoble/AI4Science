"""Compute pricing + provider selection (points 12, 13).

GPU/CPU usage is priced at the provider's own USD/hour rate (point 13: providers
define their price), converted to PWM at the shared peg (point 12: market price
+ $5/PWM). Selection picks the best eligible provider of a kind — cheapest
first among active, stake-eligible providers.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def job_cost(wall_clock_s: Optional[float], price_usd_per_hour: float) -> Dict[str, float]:
    """Cost of a compute job: hours × provider rate → USD → PWM.

    Returns {hours, usd, pwm}. Uses the shared $5/PWM peg from llm.pricing.
    """
    from ai4science.llm.pricing import usd_to_pwm
    hours = (float(wall_clock_s) / 3600.0) if wall_clock_s else 0.0
    usd = hours * float(price_usd_per_hour or 0.0)
    return {"hours": round(hours, 6), "usd": round(usd, 6), "pwm": round(usd_to_pwm(usd), 6)}


def eligible_providers(kind: Optional[str] = None) -> List["object"]:
    """Active compute providers (optionally of a kind) that pass the stake gate."""
    from ai4science.compute.registry import load_registry
    from ai4science import staking
    out = []
    for p in load_registry():
        if p.status != "active":
            continue
        if kind is not None and p.kind != kind:
            continue
        if not staking.is_eligible(p.provider_id):
            continue
        out.append(p)
    return out


def select(kind: Optional[str] = None) -> Optional["object"]:
    """Pick one eligible provider of a kind — cheapest USD/hour, then by id.

    'AI4Science can choose one GPU for one wallet' (point 12). Returns None if
    no eligible provider is available.
    """
    cands = eligible_providers(kind)
    if not cands:
        return None
    return sorted(cands, key=lambda p: (p.price_usd_per_hour, p.provider_id))[0]
