"""Compute pricing + provider selection (points 12, 13).

GPU/CPU usage is priced at the provider's own PWM/hour rate (point 13: providers
define their price, natively in PWM). Selection picks the best eligible provider
of a kind — cheapest first among active, stake-eligible providers.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def job_cost(wall_clock_s: Optional[float], pwm_per_hour: float) -> Dict[str, float]:
    """Cost of a compute job: hours × provider PWM/hour rate.

    Returns {hours, pwm}.
    """
    hours = (float(wall_clock_s) / 3600.0) if wall_clock_s else 0.0
    return {"hours": round(hours, 6),
            "pwm": round(hours * float(pwm_per_hour or 0.0), 6)}


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
    """Pick one eligible provider of a kind — cheapest PWM/hour, then by id.

    'AI4Science can choose one GPU for one wallet' (point 12). Returns None if
    no eligible provider is available.
    """
    cands = eligible_providers(kind)
    if not cands:
        return None
    return sorted(cands, key=lambda p: (p.pwm_per_hour(), p.provider_id))[0]
