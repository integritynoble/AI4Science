"""Local hot-key PWM wallet (point 6) — Phase 1, off-chain.

A locally-stored account the user spends from when using wallet-bound providers.
Phase 1 keeps it simple: a generated address + an off-chain PWM balance in
~/.config/ai4science/wallet.json (chmod 600). Balance is credited (mining /
funding) and debited (usage). Real on-chain key signing is a later phase — this
is the "middle hot-key wallet kept on the local computer" for accounting now.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Dict, Optional


def wallet_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return Path(os.environ.get("AI4SCIENCE_WALLET", base / "ai4science" / "wallet.json"))


def _new_address() -> str:
    """A 0x + 40-hex local address. (Phase 1: random, not yet an ECDSA-derived
    account — on-chain key derivation comes with the settlement layer.)"""
    return "0x" + secrets.token_hex(20)


def _save(w: Dict) -> None:
    p = wallet_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(w, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)   # 600 — it's a wallet
    except OSError:
        pass


def load() -> Optional[Dict]:
    p = wallet_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def ensure() -> Dict:
    """Return the local wallet, creating one (address, 0 balance) if absent."""
    w = load()
    if w is None:
        w = {"address": _new_address(), "balance_pwm": 0.0, "phase": "offchain-v1"}
        _save(w)
    return w


def address() -> str:
    return ensure()["address"]


def balance() -> float:
    return round(float(ensure().get("balance_pwm", 0.0)), 6)


def credit(amount: float) -> float:
    if amount < 0:
        raise ValueError("credit must be non-negative")
    w = ensure()
    w["balance_pwm"] = round(float(w.get("balance_pwm", 0.0)) + amount, 6)
    _save(w)
    return w["balance_pwm"]


def debit(amount: float) -> float:
    """Spend PWM. Raises if the balance is insufficient."""
    if amount < 0:
        raise ValueError("debit must be non-negative")
    w = ensure()
    bal = float(w.get("balance_pwm", 0.0))
    if amount > bal:
        raise ValueError(f"insufficient PWM: need {amount}, have {round(bal, 6)}")
    w["balance_pwm"] = round(bal - amount, 6)
    _save(w)
    return w["balance_pwm"]
