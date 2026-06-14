"""PWM billing for compute.

Running a job on a wallet-bound compute provider costs PWM, paid to that
provider's wallet (the third-founder address for the founder servers; the
provider's own wallet for community providers — that is how they earn PWM).
Local compute (your own machine) is free. The price is provider-set natively in
PWM/hour (the unit users actually hold); the server splits each charge 90% to
the provider, 10% to the PWM pool.
"""
from __future__ import annotations

from typing import Tuple


def compute_pwm(pwm_per_hour: float, seconds: float) -> float:
    """PWM owed for `seconds` of compute at the provider's PWM/hour price."""
    return round(max(0.0, float(pwm_per_hour)) * max(0.0, float(seconds)) / 3600.0, 6)


def _provider_pwm_rate(provider) -> float:
    """Provider's PWM/hour rate (native PWM, or legacy USD derived at the peg)."""
    fn = getattr(provider, "pwm_per_hour", None)
    if callable(fn):
        return float(fn())
    from ai4science.llm.pricing import PWM_USD
    usd = float(getattr(provider, "price_usd_per_hour", 0.0) or 0.0)
    return round(usd / PWM_USD, 6) if PWM_USD > 0 else 0.0


def charge_compute(provider, *, seconds: float, purpose: str,
                   idempotency_key: str) -> Tuple[bool, str, float]:
    """Charge PWM for compute to the provider's wallet.

    No-op (returns charged=False) for free/local compute or when the PWM gate
    is disabled (the default in dev/CI). Returns (charged, message, pwm).
    """
    pwm = compute_pwm(_provider_pwm_rate(provider), seconds)
    if pwm <= 0:
        return (False, "no charge (free / local compute)", 0.0)
    from ai4science.harness.pwm_gate import PwmGate
    gate = PwmGate.from_env()
    if not gate.enabled:
        return (False, f"PWM gate off — would charge {pwm} PWM "
                       f"to {provider.wallet_address}", pwm)
    ok, msg = gate.charge(pwm, provider.wallet_address,
                          purpose=purpose, idempotency_key=idempotency_key)
    return (ok, msg, pwm)
