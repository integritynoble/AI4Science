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

#: Kinds that are constraints rather than learned facts. They are injected
#: first and are never the entries a byte cap drops — the same rule
#: `retrieval.PROTECTED_KINDS` states for the ranked path.
PROTECTED_KINDS = frozenset(("invariant", "causal_rule"))


def _new_id() -> str:
    return f"sem_{uuid.uuid4().hex[:10]}"


def record(config: Config, agent: Agent, statement: str, *,
           kind: str = "lesson", scope: Optional[List[str]] = None,
           status: str = "active", provenance: Optional[List[str]] = None,
           contradicts: Optional[List[str]] = None,
           support_count: int = 1, tags: Optional[List[str]] = None,
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
        "support_count": int(support_count),
        "tags": list(tags or []),
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


class PromotionBlocked(Exception):
    """A candidate could not be promoted, and the reason is the message."""


def candidates(config: Config, agent: Agent) -> List[Dict[str, Any]]:
    """Entries proposed, not active, and not yet promoted.

    A promoted candidate is filtered out here rather than rewritten there: the
    log is append-only, so "already decided" is a later event, not an edit.
    """
    rows = [r for r in ledger.read(config, "semantic") if r.get("agent") == agent.id]
    promoted = {r.get("promoted_from") for r in rows if r.get("promoted_from")}
    return [r for r in rows if r.get("status") == "candidate"
            and r.get("memory_id") not in promoted]


def retract(config: Config, agent: Agent, memory_id: str,
            reason: str = "") -> Dict[str, Any]:
    """Withdraw an active entry without inventing a replacement. [§5.2]

    `promote()`'s own refusal tells the caller to "retract or supersede" the
    contradicting entry, and until now only the second was reachable — which
    forced anyone resolving a contradiction to make up a new statement they
    did not believe, just to get rid of one they no longer did.
    """
    return ledger.append(config, "semantic", {
        "schema_version": 1, "memory_id": _new_id(), "op": "retract",
        "supersedes": memory_id, "statement": "", "kind": "",
        "scope": [], "status": "retracted", "provenance": [],
        "reason": (reason or "").strip(), "agent": agent.id})


def promote(config: Config, agent: Agent, memory_id: str, *,
            by: str = "owner", resolves: Optional[List[str]] = None) -> Dict[str, Any]:
    """Make a candidate active — the only supported way one becomes true.

    Refused while the candidate carries an unresolved contradiction. The
    consolidator can and should propose a lesson that argues with something
    already believed; what it must not do is let that lesson become believed
    without the disagreement being settled. A store that holds both is not a
    memory, it is a pile, and every later retrieval has to pick one at random.

    `resolves` names the contradicting entries a caller has retracted or
    superseded first. Nothing here retracts anything on the caller's behalf:
    resolving a contradiction is a decision, and this is not the place decisions
    are made.
    """
    all_rows = [r for r in ledger.read(config, "semantic")
                if r.get("agent") == agent.id]
    rows = [r for r in all_rows if r.get("memory_id") == memory_id]
    if not rows:
        raise PromotionBlocked(f"no semantic entry {memory_id!r} for {agent.id}")
    cand = rows[-1]
    if cand.get("status") != "candidate":
        raise PromotionBlocked(
            f"{memory_id} is {cand.get('status')!r}, not a candidate — only a "
            f"candidate can be promoted")
    # Promotion is an EVENT, so the candidate row keeps saying "candidate"
    # forever — which made this repeatable, and each repeat asserted another
    # identical active entry. The promotion event is what records that the
    # candidate was consumed, and it is what makes a second call a no-op
    # instead of a duplicate. (An append-only store cannot mark the old row;
    # §2.3 is the same argument for supersession.)
    already = [r for r in all_rows
               if r.get("promoted_from") == memory_id and r.get("op") == "assert"]
    if already:
        raise PromotionBlocked(
            f"{memory_id} was already promoted, as {already[-1]['memory_id']} — "
            f"promoting it again would assert the same thing twice")
    unresolved = [c for c in (cand.get("contradicts") or [])
                  if c not in set(resolves or [])]
    still_active = {e.get("memory_id") for e in active_entries(config, agent)}
    unresolved = [c for c in unresolved if c in still_active]
    if unresolved:
        raise PromotionBlocked(
            f"{memory_id} contradicts {', '.join(unresolved)}, which is still "
            f"active. Settle the disagreement — retract or supersede the other "
            f"entry — before this becomes something I act on.")
    rec = dict(cand)
    rec.update({"memory_id": _new_id(), "op": "assert", "status": "active",
                "supersedes": None, "promoted_by": by,
                "promoted_from": memory_id,
                "provenance": list(cand.get("provenance") or []) + [memory_id]})
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
    """Format active entries for context injection. Text only.

    Prefer `render_parts()` where the caller can record what was left out —
    this wrapper exists for the many call sites that only want the block.
    """
    return render_parts(config, agent, scope_filter)[0]


def render_parts(config: Config, agent: Agent,
                 scope_filter: Optional[List[str]] = None,
                 cap: int = INJECT_BYTE_CAP):
    """The block, plus what it could not fit. Returns `(text, report)`.

    **Protected entries go first, and are never the ones dropped.** This used
    to walk the active list in ledger insertion order and stop at the byte cap,
    so an owner constraint written after sixty learned lessons was silently
    absent from the context of a consequential turn — the one failure §6.1 and
    §7.1 exist to prevent, on the one path where it matters most. Measured:
    60 lessons then one `never write to /prod` invariant, and the invariant was
    not in `W_t`.

    `report` names what was omitted and how many, so the gate can put it in the
    manifest instead of the reader assuming completeness. [§0.1.7]
    """
    entries = active_entries(config, agent, scope_filter)
    report = {"protected_total": 0, "protected_shown": 0,
              "other_total": 0, "other_shown": 0, "omitted": 0,
              "protected_dropped": 0, "ids": []}
    if not entries:
        return "", report

    protected, other = [], []
    for e in entries:
        (protected if e.get("kind") in PROTECTED_KINDS else other).append(e)
    report["protected_total"] = len(protected)
    report["other_total"] = len(other)

    lines = ["active knowledge / constraints:"]
    total_bytes = 0

    def _line(entry):
        stmt = (entry.get("statement") or "").strip()
        if not stmt:
            return None
        scope_str = ", ".join(entry.get("scope") or [])
        return f"  [{entry.get('kind', '')}] ({scope_str}) {stmt}"

    for group, key in ((protected, "protected_shown"), (other, "other_shown")):
        for entry in group:
            line = _line(entry)
            if line is None:
                continue
            if total_bytes + len(line) > cap:
                break
            lines.append(line)
            total_bytes += len(line)
            report[key] += 1
            report["ids"].append(entry.get("memory_id", ""))

    report["protected_dropped"] = report["protected_total"] - report["protected_shown"]
    report["omitted"] = ((report["protected_total"] - report["protected_shown"])
                         + (report["other_total"] - report["other_shown"]))
    if report["omitted"]:
        lines.append(
            f"  ... {report['omitted']} more active entr"
            f"{'y' if report['omitted'] == 1 else 'ies'} not shown "
            f"(byte cap {cap} reached"
            + (f"; {report['protected_dropped']} of them are CONSTRAINTS"
               if report["protected_dropped"] else "")
            + ")")
    return "\n".join(lines), report
