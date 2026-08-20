"""Conversation log for a sarsi worker — §12 "take down history".

Records every exchange (user input → worker response) to a JSONL file.
The ledger already tracks task-level events; this captures the
conversational layer: what the owner said and what the worker replied.

Format: one JSON object per line — {"at", "in", "out"}.
File: <agent_dir>/log-<surface>.jsonl  (one file per surface).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _path(agent_dir: Path, surface: str) -> Path:
    safe = "".join(c if c.isalnum() or c == "-" else "_" for c in (surface or "cli"))
    return agent_dir / f"log-{safe}.jsonl"


def append(agent_dir: Path, surface: str, user_in: str, worker_out: str) -> None:
    """Append one exchange to the surface log. Never raises."""
    try:
        p = _path(agent_dir, surface)
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "in": (user_in or "").strip(),
            "out": (worker_out or "").strip(),
        })
        with p.open("a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def read(agent_dir: Path, surface: str = "cli", limit: int = 50) -> List[Dict[str, Any]]:
    """Return the last `limit` exchanges. Returns [] if no log yet."""
    try:
        p = _path(agent_dir, surface)
        if not p.exists():
            return []
        lines = p.read_text().splitlines()
        rows = []
        for ln in lines[-limit:]:
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
        return rows
    except Exception:
        return []
