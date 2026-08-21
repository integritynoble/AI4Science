"""Semantic memory — promoted facts, lessons, invariants, causal rules.

Uses the existing ledger infrastructure (`ledger.append(config, "semantic", ...)`)
rather than a separate persistence framework, so secret filtering, timestamping,
and append discipline are inherited automatically.

Event-sourced with a materialized active view. The row is never rewritten;
supersession/retraction is a new event that references the prior item.

Schema (schema_version=1):
  {
    "schema_version": 1,
    "memory_id": "sem_...",
    "op": "assert|retract|supersede",
    "supersedes": null,          # memory_id of the prior entry this supersedes
    "statement": "...",
    "kind": "fact|lesson|invariant|causal_rule",
    "scope": ["global", "project:pwm", "task:tsk_abc"],
    "status": "candidate|active|retracted",
    "provenance": ["ep_...", "ver_..."],
    "support_count": 3,
    "contradicts": [],
    "valid_from": "...",
    "valid_until": null,
    "promoted_by": "owner|consolidator+verifier"
  }

Rules:
- one episode does not automatically become semantic truth;
- owner-explicit corrections may become active immediately if clearly scoped;
- learned candidates require repeated support or strong external evidence;
- contradictions block silent promotion;
- every active memory keeps evidence links.

Injection is scope-based, not semantic-ranked. A constraint has no vocabulary
in common with the task it constrains, so ranking it by similarity will push
it out of context exactly when it matters most.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Maximum bytes injected before announcing the remainder.
INJECT_BYTE_CAP = 4096


def _new_id() -> str:
    return f"sem_{uuid.uuid4().hex[:10]}"


def record(config: Config, agent: Agent, statement: str, *,
           kind: str = "lesson", scope: Optional[List[str]] = None,
           status: str = "active", provenance: Optional[List[str]] = None,
           contradicts: Optional[List[str]] = None,
           promoted_by: str = "owner") -> Dict[str, Any]:
    """Assert a new semantic memory entry. Returns the stored record."""
    rec = {
        "schema_version": 1,
        "memory_id": _new_id(),
        "op": "assert",
        "supersedes": None,
        "statement": statement.strip(),
        "kind": kind,
        "scope": list(scope or ["global"]),
        "status": status,
        "provenance": list(provenance or []),
        "support_count": 1,
        "contradicts": list(contradicts or []),
        "valid_from": None,   # ledger stamps `at`
        "valid_until": None,
        "promoted_by": promoted_by,
        "agent": agent.id,
    }
    return ledger.append(config, "semantic", rec)


def supersede(config: Config, agent: Agent, prior_id: str,
              new_statement: str, **kwargs) -> Dict[str, Any]:
    """Supersede an existing entry. Writes a new assert and a retraction event."""
    # Write retraction for the old entry
    ledger.append(config, "semantic", {
        "schema_version": 1,
        "memory_id": _new_id(),
        "op": "retract",
        "supersedes": prior_id,
        "statement": "",
        "kind": "retraction",
        "scope": [],
        "status": "retracted",
        "agent": agent.id,
    })
    # Write new active entry that references the old one
    kwargs.setdefault("status", "active")
    kwargs.setdefault("scope", ["global"])
    kwargs.setdefault("promoted_by", "owner")
    new_id = _new_id()
    rec = {
        "schema_version": 1,
        "memory_id": new_id,
        "op": "supersede",
        "supersedes": prior_id,
        "statement": new_statement.strip(),
        "kind": kwargs.get("kind", "lesson"),
        "scope": kwargs.get("scope", ["global"]),
        "status": kwargs.get("status", "active"),
        "provenance": kwargs.get("provenance", []),
        "support_count": kwargs.get("support_count", 1),
        "contradicts": kwargs.get("contradicts", []),
        "valid_from": None,
        "valid_until": None,
        "promoted_by": kwargs.get("promoted_by", "owner"),
        "agent": agent.id,
    }
    return ledger.append(config, "semantic", rec)


def active_entries(config: Config, agent: Agent,
                   scope_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Return the active semantic memory entries for this agent.

    The active view is computed from the full event log:
    - retract/supersede events remove the referenced entry from the active set;
    - only entries with status == "active" and not targeted by a retraction
      are included.
    Scope filter: a list of scopes to match (any overlap admits the entry).
    """
    rows = [r for r in ledger.read(config, "semantic")
            if r.get("agent") == agent.id]

    # Collect ids that have been superseded or retracted
    inactive_ids = set()
    for r in rows:
        target = r.get("supersedes")
        if target and r.get("op") in ("retract", "supersede"):
            inactive_ids.add(target)

    active = [r for r in rows
              if r.get("op") == "assert" and r.get("status") == "active"
              and r.get("memory_id") not in inactive_ids]
    # Supersede ops create both a retraction and a new entry; include the new
    # "supersede" op entries that are themselves active and not later retracted
    supersede_rows = [r for r in rows
                      if r.get("op") == "supersede"
                      and r.get("status") == "active"
                      and r.get("memory_id") not in inactive_ids]
    active.extend(supersede_rows)

    if scope_filter:
        def _matches(entry: Dict[str, Any]) -> bool:
            entry_scopes = entry.get("scope") or []
            if "global" in entry_scopes:
                return True
            return bool(set(scope_filter) & set(entry_scopes))
        active = [r for r in active if _matches(r)]

    return active


def render(config: Config, agent: Agent,
           scope_filter: Optional[List[str]] = None) -> str:
    """Format active entries for context injection.

    Entries are injected unconditionally regardless of relevance score — a
    constraint has no vocabulary in common with the task it constrains.
    Cap is announced when hit so the LLM knows to ask for the full list.
    """
    entries = active_entries(config, agent, scope_filter)
    if not entries:
        return ""

    lines = ["active knowledge / constraints:"]
    total_bytes = 0
    shown = 0
    for entry in entries:
        stmt = (entry.get("statement") or "").strip()
        if not stmt:
            continue
        kind = entry.get("kind", "")
        scope_str = ", ".join(entry.get("scope") or [])
        line = f"  [{kind}] ({scope_str}) {stmt}"
        if total_bytes + len(line) > INJECT_BYTE_CAP:
            remaining = len(entries) - shown
            lines.append(f"  ... {remaining} more active entr{'y' if remaining == 1 else 'ies'} "
                         f"not shown (byte cap {INJECT_BYTE_CAP} reached)")
            break
        lines.append(line)
        total_bytes += len(line)
        shown += 1

    return "\n".join(lines)
