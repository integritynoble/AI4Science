"""Prediction registry — register expected outcomes before actions; score after.

A prediction is registered before a consequential action (ses.assign, a tool
call, a phase). After the action completes, the outcome is scored. Records are
immutable once scored — history cannot be rewritten.

The log is event-sourced and append-only:
  {"type": "prediction", "id": "pred_0001", "at": "...", "task_id": "...",
   "action": "assign session", "expected": "phase 1 completes", "check": "..."}
  {"type": "score", "pred_id": "pred_0001", "outcome": "PASS",
   "error": "", "scored_at": "..."}

Calibration reads scored pairs and reports hit rate by task class (coarse bucket
derived from the action string).

File: <agent_dir>/predictions.jsonl
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _path(agent_dir: Path) -> Path:
    return agent_dir / "predictions.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_all(agent_dir: Path) -> List[Dict[str, Any]]:
    p = _path(agent_dir)
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def _append(agent_dir: Path, rec: Dict[str, Any]) -> None:
    p = _path(agent_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _new_id(records: List[Dict[str, Any]]) -> str:
    nums = []
    for r in records:
        if r.get("type") == "prediction":
            try:
                nums.append(int((r.get("id") or "").split("_", 1)[1]))
            except Exception:
                pass
    return f"pred_{max(nums, default=0) + 1:04d}"


def register(agent_dir: Path, task_id: str, action: str,
             expected: str, check: str = "") -> Dict[str, Any]:
    """Register a prediction before a consequential action. Returns the entry."""
    records = _read_all(agent_dir)
    pred: Dict[str, Any] = {
        "type": "prediction",
        "id": _new_id(records),
        "at": _now_iso(),
        "task_id": (task_id or "").strip(),
        "action": action.strip(),
        "expected": expected.strip(),
        "check": (check or "").strip(),
    }
    _append(agent_dir, pred)
    return pred


def score(agent_dir: Path, pred_id: str, outcome: str,
          error: str = "") -> Optional[Dict[str, Any]]:
    """Score a prediction. Returns the score record, or None on error.

    Fails (returns None) when pred_id does not exist or is already scored —
    the log is immutable after scoring.
    """
    records = _read_all(agent_dir)
    # Check pred exists
    pred = next((r for r in records
                 if r.get("type") == "prediction" and r.get("id") == pred_id), None)
    if pred is None:
        return None
    # Check not already scored
    already = next((r for r in records
                    if r.get("type") == "score" and r.get("pred_id") == pred_id), None)
    if already is not None:
        return None  # immutable — already scored
    rec: Dict[str, Any] = {
        "type": "score",
        "pred_id": pred_id,
        "outcome": (outcome or "").strip().upper(),
        "error": (error or "").strip(),
        "scored_at": _now_iso(),
    }
    _append(agent_dir, rec)
    return rec


def get(agent_dir: Path, pred_id: str) -> Optional[Dict[str, Any]]:
    """Return the prediction entry plus its score if it has one."""
    records = _read_all(agent_dir)
    pred = next((r for r in records
                 if r.get("type") == "prediction" and r.get("id") == pred_id), None)
    if pred is None:
        return None
    sc = next((r for r in records
               if r.get("type") == "score" and r.get("pred_id") == pred_id), None)
    return dict(pred, score=sc)


def unscored(agent_dir: Path) -> List[Dict[str, Any]]:
    """Predictions that have not yet been scored."""
    records = _read_all(agent_dir)
    scored_ids = {r["pred_id"] for r in records if r.get("type") == "score"}
    return [r for r in records
            if r.get("type") == "prediction" and r["id"] not in scored_ids]


def _task_class(action: str) -> str:
    """Coarse task class from the action string for calibration bucketing."""
    a = (action or "").lower()
    if "assign" in a or "session" in a:
        return "session"
    if "plan" in a or "draft" in a:
        return "planning"
    if "verif" in a or "check" in a or "phase" in a:
        return "verification"
    return "other"


def calibration(agent_dir: Path,
                task_class: Optional[str] = None) -> Dict[str, Any]:
    """Hit rate of scored predictions, optionally filtered by task class.

    A hit is a prediction whose outcome == 'PASS'. Returns
    {"n": int, "hits": int, "rate": float|None} — rate is None when n==0.
    """
    records = _read_all(agent_dir)
    preds = {r["id"]: r for r in records if r.get("type") == "prediction"}
    scores = {r["pred_id"]: r for r in records if r.get("type") == "score"}

    pairs = [(preds[pid], scores[pid])
             for pid in preds if pid in scores]
    if task_class:
        pairs = [(p, s) for p, s in pairs
                 if _task_class(p.get("action", "")) == task_class]

    n = len(pairs)
    hits = sum(1 for _, s in pairs if s.get("outcome") == "PASS")
    return {"n": n, "hits": hits, "rate": hits / n if n else None}


def render(agent_dir: Path) -> str:
    """Calibration summary for self-model injection."""
    cal = calibration(agent_dir)
    if cal["n"] == 0:
        return ""
    rate = cal["rate"]
    rate_str = f"{rate:.0%}" if rate is not None else "n/a"
    pending = len(unscored(agent_dir))
    lines = [f"prediction calibration: {cal['hits']}/{cal['n']} matched "
             f"({rate_str})"]
    if pending:
        lines.append(f"  {pending} prediction(s) awaiting scoring")
    return "\n".join(lines)
