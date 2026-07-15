"""The trust ledger — the earned-A3 accounting.

A3 (full autonomy: even unclassifiable commands run, catastrophe backstop kept)
is not a setting the owner flips — it is *earned*. This ledger counts the owner's
decisions across every approval point; once enough consequential actions have been
approved with zero catastrophe attempts, A3 becomes eligible, and the owner may
then explicitly unlock it. Fail-safe: reads/writes never raise.

State: `$PWM_CP_STATE_DIR/pwm-cc-trust/<owner>.json`. Owner defaults to
`PWM_TRUST_OWNER` or the OS user. Threshold: `PWM_A3_THRESHOLD` (default 50).
"""
from __future__ import annotations

import datetime
import getpass
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict

_OUTCOME_FIELD = {"approve": "approvals", "deny": "denials", "forbidden": "forbidden_trips"}


def _trust_dir() -> Path:
    base = os.environ.get("PWM_CP_STATE_DIR") or tempfile.gettempdir()
    return Path(base) / "pwm-cc-trust"


def _owner() -> str:
    if os.environ.get("PWM_TRUST_OWNER"):
        return os.environ["PWM_TRUST_OWNER"]
    try:
        return getpass.getuser() or "owner"
    except Exception:
        return "owner"


def _path() -> Path:
    return _trust_dir() / f"{_owner()}.json"


def _threshold() -> int:
    try:
        return int(os.environ.get("PWM_A3_THRESHOLD", "50"))
    except (ValueError, TypeError):
        return 50


def _default() -> Dict[str, Any]:
    return {"approvals": 0, "denials": 0, "forbidden_trips": 0,
            "a3_unlocked": False, "updated": None}


def _iso(t: float) -> str:
    return (datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc)
            .replace(microsecond=0).isoformat())


def status() -> Dict[str, Any]:
    """The current ledger (defaults when none exists yet)."""
    try:
        data = json.loads(_path().read_text())
        merged = _default()
        merged.update({k: data[k] for k in _default() if k in data})
        return merged
    except Exception:
        return _default()


def _write(s: Dict[str, Any]) -> None:
    try:
        _trust_dir().mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(s, indent=2))
    except Exception:
        pass


def record(outcome: str, *, now: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Record one owner decision: 'approve' | 'deny' | 'forbidden'. Fail-safe."""
    field = _OUTCOME_FIELD.get(outcome)
    s = status()
    if field:
        s[field] = int(s.get(field, 0)) + 1
        s["updated"] = _iso(now())
        _write(s)
    return s


def is_a3_eligible() -> bool:
    s = status()
    return int(s.get("approvals", 0)) >= _threshold() and int(s.get("forbidden_trips", 0)) == 0


def a3_unlocked() -> bool:
    return bool(status().get("a3_unlocked"))


def unlock_a3() -> Dict[str, Any]:
    """Owner elects A3 — allowed only once eligible. Returns {ok, reason}."""
    s = status()
    if s.get("a3_unlocked"):
        return {"ok": True, "reason": "already unlocked", **s}
    if not is_a3_eligible():
        return {"ok": False, "reason": f"A3 locked: {int(s.get('approvals', 0))}/{_threshold()} "
                                       f"approvals, {int(s.get('forbidden_trips', 0))} catastrophe "
                                       f"attempt(s)", **s}
    s["a3_unlocked"] = True
    _write(s)
    return {"ok": True, "reason": "A3 unlocked", **s}


def relock_a3() -> Dict[str, Any]:
    """Owner revokes A3 (drop back to the earned ceiling). Fail-safe."""
    s = status()
    s["a3_unlocked"] = False
    _write(s)
    return {"ok": True, **s}


def effective_ceiling(requested: str) -> str:
    """The chokepoint: a requested A3 is honored only when A3 is unlocked;
    otherwise it is capped to A2. Other ceilings pass through unchanged."""
    if requested == "A3" and not a3_unlocked():
        return "A2"
    return requested


def threshold() -> int:
    return _threshold()
