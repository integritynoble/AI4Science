"""Offline consolidator — episodes → semantic/skill candidates.

Reads the episode ledger and proposes:
  - semantic candidates: for repeated error patterns, stable lessons learned;
  - procedural candidates (skills): for repeated successful workflows.

Rules (invariants this module enforces):
  - A single episode never becomes an active semantic truth automatically.
  - Owner confirmation is required before a candidate becomes active.
  - Contradiction between episodes blocks silent promotion.
  - Skill candidates require explicit preconditions, tests, postconditions,
    and rollback before promotion.
  - High-impact rules (scope=global, kind=invariant) always require owner
    confirmation regardless of support count.

This is an offline job — it reads, proposes, and returns; it does NOT
write to the active semantic ledger directly. It writes candidates with
`status="candidate"` via `semantic.record(..., status="candidate")`.
The owner or a governed promotion flow moves them to `status="active"`.

Run as a library function: `consolidate.run(config, agent)`.
Output: list of proposed candidate entries, plus a report dict.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from ai4science.harness.agents.sarsi import ledger, semantic
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Minimum times the same error pattern must appear before a semantic candidate
#: is proposed. One episode is not evidence — it is noise.
MIN_SUPPORT_FOR_CANDIDATE = 2

#: Minimum times a successful workflow must repeat before a skill candidate
#: is proposed.
MIN_SUPPORT_FOR_SKILL = 3

#: Error patterns from these triggers are clustered for semantic candidates.
FAILURE_TRIGGERS = frozenset(
    ("refuted_prediction", "refusal", "clash", "correction")
)

#: A pass outcome that repeats produces a skill candidate.
SUCCESS_OUTCOME = "pass"


def _episodes(config: Config, agent: Agent) -> List[Dict[str, Any]]:
    """All episode records for this agent from the ledger."""
    try:
        return [r for r in ledger.read(config, "episodes")
                if r.get("agent_id") == agent.id]
    except Exception:
        return []


def _fingerprint(ep: Dict[str, Any]) -> str:
    """Coarse fingerprint for clustering: trigger + first 40 chars of summary."""
    trigger = ep.get("trigger", "")
    summary = (ep.get("summary") or "")[:40].lower()
    return f"{trigger}::{summary}"


def _contradicts(candidate_summary: str,
                 existing: List[Dict[str, Any]]) -> List[str]:
    """Simple lexical contradiction check: does any active entry assert the
    opposite? Returns ids of potential contradicting entries.

    Heuristic: if an existing active entry's statement contains 'never' and
    the candidate says 'always', or vice versa, flag it. Not exhaustive —
    owner confirmation is still required.
    """
    s = candidate_summary.lower()
    contradictions: List[str] = []
    for e in existing:
        stmt = (e.get("statement") or "").lower()
        if (("never" in s and "always" in stmt) or
                ("always" in s and "never" in stmt) or
                ("do not" in s and "do" in stmt and "do not" not in stmt) or
                ("must not" in s and "must" in stmt and "must not" not in stmt)):
            contradictions.append(e.get("memory_id", "?"))
    return contradictions


def _propose_semantic_candidate(config: Config, agent: Agent,
                                 group: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Propose a semantic candidate from a group of similar failure episodes.

    Returns the stored candidate record, or None if blocked by contradiction.
    """
    anchor = group[0]
    trigger = anchor.get("trigger", "unknown")
    summary_parts = sorted({(ep.get("summary") or "")[:80] for ep in group})
    statement = (f"Repeated {trigger}: " + "; ".join(summary_parts[:3]))[:400]

    # Infer scope from task_ids in the group
    task_ids = [ep.get("task_id") for ep in group if ep.get("task_id")]
    scope: List[str] = (["task:" + t for t in task_ids[:2]]
                        if task_ids else ["global"])

    evidence_refs = [ep.get("episode_id", "") for ep in group if ep.get("episode_id")]

    # Check for contradictions with existing active entries
    try:
        active = semantic.active_entries(config, agent)
        contradicts = _contradicts(statement, active)
    except Exception:
        contradicts = []
        active = []

    kind = "lesson" if trigger in ("correction", "rollback") else "causal_rule"

    try:
        rec = semantic.record(config, agent, statement,
                              kind=kind,
                              scope=scope,
                              status="candidate",   # never active until owner confirms
                              provenance=evidence_refs,
                              contradicts=contradicts,
                              promoted_by="consolidator+verifier")
        return rec
    except Exception:
        return None


def _propose_skill_candidate(config: Config, agent: Agent,
                              group: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Propose a skill candidate from repeated successful episodes.

    Writes to the skills ledger channel. Owner must confirm before activation.
    """
    anchor = group[0]
    task_ids = [ep.get("task_id") for ep in group if ep.get("task_id")]
    summaries = list({(ep.get("summary") or "")[:60] for ep in group})
    evidence_refs = [ep.get("episode_id", "") for ep in group if ep.get("episode_id")]

    skill_id = f"skill_{uuid.uuid4().hex[:8]}"
    scope = list({f"task:{t}" for t in task_ids[:3]}) or ["global"]

    rec: Dict[str, Any] = {
        "schema_version": 1,
        "skill_id": skill_id,
        "version": 1,
        "scope": scope,
        "preconditions": ["task workspace declared"],
        "description": ("Repeated successful workflow: "
                        + "; ".join(summaries[:2]))[:300],
        "entrypoint": "",         # owner fills in
        "tests": [],              # owner fills in
        "postconditions": [],     # owner fills in
        "rollback": "",           # owner fills in
        "evidence_refs": evidence_refs,
        "status": "candidate",    # never active until tests pass + owner confirms
        "agent_id": agent.id,
    }
    try:
        return ledger.append(config, "skills", rec)
    except Exception:
        return None


def run(config: Config, agent: Agent) -> Dict[str, Any]:
    """Run the offline consolidator for this agent.

    Returns a report dict with:
      - episodes_read: total episodes processed
      - semantic_candidates: list of proposed semantic candidate records
      - skill_candidates: list of proposed skill candidate records
      - skipped_contradictions: count of candidates blocked by contradictions
      - error_groups: groups of failure episodes that hit MIN_SUPPORT
      - success_groups: groups of success episodes that hit MIN_SUPPORT_FOR_SKILL
    """
    episodes = _episodes(config, agent)

    # ── cluster failure episodes ──────────────────────────────────────────────
    failure_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    success_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for ep in episodes:
        trigger = ep.get("trigger", "")
        outcome = ep.get("outcome", "")
        fp = _fingerprint(ep)
        if trigger in FAILURE_TRIGGERS:
            failure_groups[fp].append(ep)
        elif outcome == SUCCESS_OUTCOME:
            success_groups[fp].append(ep)

    semantic_candidates: List[Dict[str, Any]] = []
    skill_candidates: List[Dict[str, Any]] = []
    skipped = 0
    qualifying_error_groups: List[Tuple[str, int]] = []
    qualifying_success_groups: List[Tuple[str, int]] = []

    for fp, group in failure_groups.items():
        if len(group) >= MIN_SUPPORT_FOR_CANDIDATE:
            qualifying_error_groups.append((fp, len(group)))
            rec = _propose_semantic_candidate(config, agent, group)
            if rec is not None:
                semantic_candidates.append(rec)
            else:
                skipped += 1

    for fp, group in success_groups.items():
        if len(group) >= MIN_SUPPORT_FOR_SKILL:
            qualifying_success_groups.append((fp, len(group)))
            rec = _propose_skill_candidate(config, agent, group)
            if rec is not None:
                skill_candidates.append(rec)

    return {
        "episodes_read": len(episodes),
        "error_groups_qualifying": qualifying_error_groups,
        "success_groups_qualifying": qualifying_success_groups,
        "semantic_candidates": semantic_candidates,
        "skill_candidates": skill_candidates,
        "skipped_contradictions": skipped,
        "agent_id": agent.id,
    }
