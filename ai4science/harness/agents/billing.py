"""Wallet charging for plug-in agents/tools — reuse the agent-pool + PWM gate.

A plug-in (manifest with a `wallet`) earns two ways, both off by default
(disabled unless the PWM gate is on, so dev/CI run free):

  1. **Direct charge** — a confirmed paid use debits the user `price_pwm` and
     credits the plug-in's wallet (the marketplace fee its author set).
  2. **Pool reward** — the same use is logged as agent-pool usage, so the weekly
     emission also pays the author from the agent pool (w_k = usage × quality).

Both go through the existing PwmGate; no new economics here.
"""
from __future__ import annotations

from typing import List, Optional

from ai4science.harness.agents.spec import AgentSpec


def _gate(gate=None):
    if gate is not None:
        return gate
    from ai4science.harness.pwm_gate import PwmGate
    return PwmGate.from_env()


def register_plugin_contribution(spec: AgentSpec, *, agent_name: Optional[str] = None,
                                 gate=None) -> bool:
    """Register a plug-in as an agent-pool contribution so its usage earns PWM for
    its wallet. Best-effort; no-op when the gate is off or the plug-in has no
    wallet. `agent_name` is the pool the contribution belongs to (defaults to the
    plug-in's own name — its own pool)."""
    if not spec.wallet:
        return False
    g = _gate(gate)
    if not getattr(g, "enabled", False):
        return False
    ctype = "agent" if spec.category != "tool" else "tool"
    try:
        status, _ = g._post("/api/v1/agent-pool/contributions", {
            "contribution_id": spec.name,
            "agent_name": agent_name or spec.name,
            "ctype": ctype,
            "author_wallet": spec.wallet,
            "title": spec.title,
        })
        return status < 400
    except Exception:
        return False


def charge_plugin_use(spec: AgentSpec, *, turn_id: str, agent_name: Optional[str] = None,
                      gate=None) -> List[str]:
    """On a confirmed paid use of a plug-in: charge `price_pwm` to its wallet and
    log pool usage. Returns human-readable notes (empty when the gate is off or
    there's nothing to charge). Idempotent per `turn_id`."""
    notes: List[str] = []
    if not spec.wallet:
        return notes
    g = _gate(gate)
    if not getattr(g, "enabled", False):
        return notes
    pool = agent_name or spec.name
    if spec.price_pwm and spec.price_pwm > 0:
        ok, msg = g.charge(spec.price_pwm, provider_wallet=spec.wallet,
                           purpose=f"plugin:{spec.name}",
                           idempotency_key=f"pluginuse:{spec.name}:{turn_id}")
        notes.append(f"charged {spec.price_pwm:g} PWM to {spec.wallet}"
                     if ok else (msg or "charge failed"))
    if g.post_usage(contribution_id=spec.name, agent_name=pool, turn_id=turn_id):
        notes.append("logged pool usage")
    return notes
