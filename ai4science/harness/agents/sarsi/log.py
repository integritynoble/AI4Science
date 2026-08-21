"""Conversation log for a sarsi worker — §12 "take down history".

Records every exchange (user input → worker response) to a JSONL file.
The ledger already tracks task-level events; this captures the
conversational layer: what the owner said and what the worker replied.

Format: one JSON object per line.
Required fields: {schema_version, exchange_id, at, in, out}.
Optional fields: {task_id, trigger}.
File: <agent_dir>/log-<surface>.jsonl  (one file per surface).

Old rows without exchange_id or schema_version are read compatibly;
readers must normalize missing fields rather than failing on them.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _path(agent_dir: Path, surface: str) -> Path:
    safe = "".join(c if c.isalnum() or c == "-" else "_" for c in (surface or "cli"))
    return agent_dir / f"log-{safe}.jsonl"


def _new_exchange_id() -> str:
    return f"x_{uuid.uuid4().hex[:8]}"


def append(agent_dir: Path, surface: str, user_in: str, worker_out: str,
           task_id: str = "", trigger: str = "",
           exchange_id: str = "") -> None:
    """Append one exchange to the surface log. Never raises.

    exchange_id: stable id for this exchange; auto-generated if not provided.
    task_id: groups episodes by task for semantic consolidation (M1).
    trigger: marks exchanges that fired a memory trigger (W4).
    """
    try:
        p = _path(agent_dir, surface)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec: Dict[str, Any] = {
            "schema_version": 1,
            "exchange_id": exchange_id or _new_exchange_id(),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "in": (user_in or "").strip(),
            "out": (worker_out or "").strip(),
        }
        if task_id:
            rec["task_id"] = task_id
        if trigger:
            rec["trigger"] = trigger
        with p.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def read(agent_dir: Path, surface: str = "cli",
         limit: int = 50) -> List[Dict[str, Any]]:
    """Return the last `limit` exchanges, or all entries when limit=0.

    Entries are returned oldest-first so the reader sees them in chronological
    order; use [-N:] on the result to get the most recent N.
    """
    try:
        p = _path(agent_dir, surface)
        if not p.exists():
            return []
        lines = p.read_text().splitlines()
        tail = lines if limit == 0 else lines[-limit:]
        rows = []
        for ln in tail:
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
        return rows
    except Exception:
        return []
