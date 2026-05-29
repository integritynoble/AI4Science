"""Provider stake / collateral — the no-burn hold-reason.

Providers lock PWM as collateral to participate; stake is slashed for
unverified / bad results (the deterministic judge decides). Locking supply is
the scarcity engine of the no-burn token model
(pwm-team/funds/PWM_TOKEN_ECONOMICS_NOBURN_VARIANT). Off-chain accounting only —
the CLI moves no real tokens; on-chain staking is a later, governance-gated step.

Eligibility: a provider may serve/earn only if its staked PWM >= MIN_STAKE_PWM,
EXCEPT founder-tier providers, which bootstrap trust without staking.

Storage is an append-only JSONL of events (stake / unstake / slash); the staked
balance is derived by summing, so the full history is auditable.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Minimum stake (PWM) for a non-founder provider to be eligible.
MIN_STAKE_PWM = float(os.environ.get("AI4SCIENCE_MIN_STAKE_PWM", "100"))


def default_path() -> Path:
    override = os.environ.get("AI4SCIENCE_STAKE_LEDGER")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai4science" / "stakes.jsonl"


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _provider_lookup(provider_id: str):
    """Find a provider (LLM or compute) by id, for wallet + tier."""
    try:
        from ai4science.llm.registry import get_provider as get_llm
        p = get_llm(provider_id)
        if p is not None:
            return p
    except Exception:
        pass
    try:
        from ai4science.compute.registry import get_provider as get_compute
        return get_compute(provider_id)
    except Exception:
        return None


def provider_wallet(provider_id: str) -> Optional[str]:
    p = _provider_lookup(provider_id)
    return getattr(p, "wallet_address", None) if p else None


def provider_tier(provider_id: str) -> str:
    p = _provider_lookup(provider_id)
    return getattr(p, "trust_tier", "open") if p else "open"


def load(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = path or default_path()
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _append(event: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def staked(provider_id: str, path: Optional[Path] = None) -> float:
    """Net staked PWM = sum(stake) − sum(unstake) − sum(slash)."""
    bal = 0.0
    for e in load(path):
        if e.get("provider_id") != provider_id:
            continue
        amt = e.get("amount") or 0.0
        bal += amt if e.get("kind") == "stake" else -amt
    return round(bal, 6)


def slashed_total(provider_id: str, path: Optional[Path] = None) -> float:
    return round(sum(e.get("amount") or 0.0 for e in load(path)
                     if e.get("provider_id") == provider_id and e.get("kind") == "slash"), 6)


def stake(provider_id: str, amount: float, wallet: Optional[str] = None,
          path: Optional[Path] = None) -> float:
    if amount <= 0:
        raise ValueError("stake amount must be positive")
    _append({"ts": _utcnow(), "provider_id": provider_id,
             "wallet": wallet or provider_wallet(provider_id),
             "kind": "stake", "amount": float(amount), "reason": ""}, path)
    return staked(provider_id, path)


def unstake(provider_id: str, amount: float, path: Optional[Path] = None) -> float:
    if amount <= 0:
        raise ValueError("unstake amount must be positive")
    bal = staked(provider_id, path)
    if amount > bal:
        raise ValueError(f"cannot unstake {amount} PWM; only {bal} staked")
    _append({"ts": _utcnow(), "provider_id": provider_id,
             "wallet": provider_wallet(provider_id),
             "kind": "unstake", "amount": float(amount), "reason": ""}, path)
    return staked(provider_id, path)


def slash(provider_id: str, amount: float, reason: str,
          path: Optional[Path] = None) -> float:
    if amount <= 0:
        raise ValueError("slash amount must be positive")
    bal = staked(provider_id, path)
    amount = min(float(amount), bal)   # never slash below zero
    _append({"ts": _utcnow(), "provider_id": provider_id,
             "wallet": provider_wallet(provider_id),
             "kind": "slash", "amount": amount, "reason": reason}, path)
    return staked(provider_id, path)


def is_eligible(provider_id: str, path: Optional[Path] = None) -> bool:
    """Founders bootstrap without stake; everyone else needs >= MIN_STAKE_PWM."""
    if provider_tier(provider_id) == "founder":
        return True
    return staked(provider_id, path) >= MIN_STAKE_PWM


def summary(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    ids = {e.get("provider_id") for e in load(path) if e.get("provider_id")}
    out = {}
    for pid in ids:
        out[pid] = {
            "staked": staked(pid, path),
            "slashed": slashed_total(pid, path),
            "tier": provider_tier(pid),
            "eligible": is_eligible(pid, path),
        }
    return out
