"""LLM-consumption ledger (design point 6).

Append-only JSONL recording each metered call: tokens, USD, PWM, and the
provider wallet the usage is attributed to. `summary()` rolls it up per wallet
(what each provider has earned in PWM) and overall.

Off-chain accounting only — on-chain PWM settlement is a later, platform-owned,
multisig-gated step. The CLI never moves tokens.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def default_path() -> Path:
    override = os.environ.get("AI4SCIENCE_LLM_LEDGER")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai4science" / "llm_ledger.jsonl"


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def record(*, agent: str, backend: str, model: str, wallet: Optional[str],
           usage: Dict[str, Any], cost: Dict[str, float],
           path: Optional[Path] = None) -> None:
    """Append one metered call. Defensive — never raises into the caller."""
    path = path or default_path()
    entry = {
        "ts": _utcnow(), "agent": agent, "backend": backend, "model": model,
        "wallet": wallet,
        "input_tokens": usage.get("input"), "output_tokens": usage.get("output"),
        "total_tokens": usage.get("total"),
        "usd_official": cost.get("usd_official"),
        "usd_billed": cost.get("usd_billed"),
        "pwm": cost.get("pwm"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


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


def summary(path: Optional[Path] = None) -> Dict[str, Any]:
    """Per-wallet PWM + USD totals and a grand total."""
    rows = load(path)
    per_wallet: Dict[str, Dict[str, float]] = {}
    tot_pwm = tot_usd = 0.0
    calls = 0
    for r in rows:
        w = r.get("wallet") or "(unattributed)"
        agg = per_wallet.setdefault(w, {"pwm": 0.0, "usd_billed": 0.0, "calls": 0})
        agg["pwm"] += r.get("pwm") or 0.0
        agg["usd_billed"] += r.get("usd_billed") or 0.0
        agg["calls"] += 1
        tot_pwm += r.get("pwm") or 0.0
        tot_usd += r.get("usd_billed") or 0.0
        calls += 1
    return {"per_wallet": per_wallet, "total_pwm": round(tot_pwm, 6),
            "total_usd_billed": round(tot_usd, 6), "calls": calls}
