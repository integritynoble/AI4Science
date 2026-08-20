"""Semantic memory — consolidated stable facts, decisions, constraints.

Episodic memory (log-cli.jsonl) captures individual exchanges; semantic memory
captures what survives across them: decisions, constraints, preferences, facts,
and open issues. Unlike episodes, semantic entries are promoted explicitly and
supersede each other — a constraint that has changed is not deleted, it is
marked superseded and points to its replacement.

**Always inject all active entries** — constraints and decisions must not be
missed by a relevance gate. This is the one memory class that bypasses the
working-memory gate (M2).

File: <agent_dir>/semantic.jsonl — one JSON object per line.

Entry shape:
  {
    "id":           "sem_0001",
    "type":         "constraint|decision|preference|fact|open_issue",
    "scope":        "global|project:<name>|task:<id>",
    "text":         "Never auto-push to main without user approval",
    "importance":   10,
    "status":       "active|superseded",
    "superseded_by": null,
    "evidence_ref": "ex_183",
    "at":           "2026-08-20T09:00:00Z"
  }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VALID_TYPES = frozenset(("constraint", "decision", "preference", "fact",
                         "open_issue"))


def _path(agent_dir: Path) -> Path:
    return agent_dir / "semantic.jsonl"


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


def _write_all(agent_dir: Path, entries: List[Dict[str, Any]]) -> None:
    p = _path(agent_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(e) for e in entries) + ("\n" if entries else "")
    )


def _new_id(existing: List[Dict[str, Any]]) -> str:
    nums = []
    for e in existing:
        try:
            nums.append(int((e.get("id") or "").split("_", 1)[1]))
        except Exception:
            pass
    return f"sem_{max(nums, default=0) + 1:04d}"


def record(agent_dir: Path, type_: str, scope: str, text: str,
           importance: int = 5, evidence_ref: str = "") -> Dict[str, Any]:
    """Write a new active semantic entry. Returns the entry written."""
    if type_ not in VALID_TYPES:
        raise ValueError(f"type must be one of {sorted(VALID_TYPES)!r}")
    existing = _read_all(agent_dir)
    entry: Dict[str, Any] = {
        "id": _new_id(existing),
        "type": type_,
        "scope": (scope or "global").strip(),
        "text": text.strip(),
        "importance": int(importance),
        "status": "active",
        "superseded_by": None,
        "evidence_ref": (evidence_ref or "").strip(),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    existing.append(entry)
    _write_all(agent_dir, existing)
    return entry


def supersede(agent_dir: Path, old_id: str, new_text: str,
              type_: str = "", scope: str = "", importance: int = 0,
              evidence_ref: str = "") -> Optional[Dict[str, Any]]:
    """Replace old_id with a new entry that supersedes it.

    The old entry's status becomes "superseded" and points to the new id.
    Fields not provided are inherited from the old entry.
    Returns the new entry, or None when old_id is not found.
    """
    existing = _read_all(agent_dir)
    old = next((e for e in existing if e.get("id") == old_id), None)
    if old is None:
        return None
    new_entry: Dict[str, Any] = {
        "id": _new_id(existing),
        "type": type_ or old.get("type", "fact"),
        "scope": (scope or old.get("scope") or "global").strip(),
        "text": new_text.strip(),
        "importance": int(importance) if importance else old.get("importance", 5),
        "status": "active",
        "superseded_by": None,
        "evidence_ref": (evidence_ref or "").strip(),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    old["status"] = "superseded"
    old["superseded_by"] = new_entry["id"]
    existing.append(new_entry)
    _write_all(agent_dir, existing)
    return new_entry


def active_entries(agent_dir: Path) -> List[Dict[str, Any]]:
    """All entries whose status is 'active', sorted by importance descending."""
    rows = [e for e in _read_all(agent_dir) if e.get("status") == "active"]
    return sorted(rows, key=lambda e: -int(e.get("importance", 0)))


def get(agent_dir: Path, entry_id: str) -> Optional[Dict[str, Any]]:
    """Look up any entry by id (active or superseded)."""
    return next(
        (e for e in _read_all(agent_dir) if e.get("id") == entry_id), None
    )


def render(agent_dir: Path) -> str:
    """Active entries formatted for injection into context.

    Always inject everything — constraints must not be missed by a relevance
    gate. An empty string means no semantic entries exist yet.
    """
    entries = active_entries(agent_dir)
    if not entries:
        return ""
    lines = [f"semantic memory ({len(entries)} active {'entry' if len(entries) == 1 else 'entries'}):"]
    for e in entries:
        tag = f"[{e.get('type', '?')}:{e.get('scope', 'global')}]"
        lines.append(f"  {e['id']} {tag} {e.get('text', '')}")
    return "\n".join(lines)
