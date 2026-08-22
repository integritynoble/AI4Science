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


class SkillPromotionError(Exception):
    """A skill candidate failed the promotion gate."""


def promote_skill(config: Config, agent: Agent, skill_id: str,
                  sandbox_exit_code: int = 0) -> Dict[str, Any]:
    """Promote a skill candidate to active status (M5.4).

    A procedural candidate becomes active ONLY after all of the following are
    satisfied — these are checked here, not trusted from the candidate record:

      1. preconditions: non-empty list.
      2. tests: non-empty list AND all tests passed in sandbox
         (caller provides sandbox_exit_code — 0 means all tests passed).
      3. postconditions: non-empty list.
      4. rollback: non-empty string.
      5. evidence_refs: non-empty list.

    Any violation raises SkillPromotionError — the skill remains a candidate.
    On success, writes an activate event to the skills ledger.

    This function enforces the gate; it does NOT run the sandbox itself.
    The caller is responsible for running the declared tests and passing the
    exit code.  A caller that fabricates exit_code=0 without running tests
    is violating the protocol — this is the same as the worker grading its
    own work, which the authority kernel prohibits.
    """
    # The LAST event for this skill, not the first. An append-only ledger keeps
    # the `propose` row forever, so reading the first match let an already
    # active skill be promoted again — and each promotion writes another
    # `activate`. In an append-only log the state is the last row; anything
    # else reads history as if it were the present.
    rows = [s for s in ledger.read(config, "skills")
            if s.get("skill_id") == skill_id and s.get("agent_id") == agent.id]
    candidate = rows[-1] if rows else None
    if candidate is None:
        raise SkillPromotionError(
            f"skill {skill_id!r} not found for agent {agent.id!r}")
    if candidate.get("status") != "candidate":
        raise SkillPromotionError(
            f"skill {skill_id!r} has status {candidate.get('status')!r}; "
            "only candidates can be promoted")
    if not candidate.get("preconditions"):
        raise SkillPromotionError(
            f"skill {skill_id!r}: preconditions must be explicit before promotion")
    if not candidate.get("tests"):
        raise SkillPromotionError(
            f"skill {skill_id!r}: tests must be declared and run in sandbox "
            "before promotion — a skill with no tests cannot be promoted")
    if sandbox_exit_code != 0:
        raise SkillPromotionError(
            f"skill {skill_id!r}: sandbox tests failed (exit code "
            f"{sandbox_exit_code}) — fix tests before promoting")
    if not candidate.get("postconditions"):
        raise SkillPromotionError(
            f"skill {skill_id!r}: postconditions must be declared before promotion")
    if not candidate.get("rollback"):
        raise SkillPromotionError(
            f"skill {skill_id!r}: rollback procedure must be defined before promotion")
    if not candidate.get("evidence_refs"):
        raise SkillPromotionError(
            f"skill {skill_id!r}: evidence links must be recorded before promotion")

    activation: Dict[str, Any] = {
        "schema_version": 1,
        "skill_id": skill_id,
        "version": candidate.get("version", 1),
        "op": "activate",
        "status": "active",
        "agent_id": agent.id,
        "preconditions": candidate["preconditions"],
        "tests": candidate["tests"],
        "postconditions": candidate["postconditions"],
        "rollback": candidate["rollback"],
        "evidence_refs": candidate["evidence_refs"],
        "sandbox_exit_code": sandbox_exit_code,
        "description": candidate.get("description", ""),
        "scope": candidate.get("scope", ["global"]),
    }
    return ledger.append(config, "skills", activation)


def active_skills(config: Config, agent: Agent) -> List[Dict[str, Any]]:
    """Return currently active skills for this agent.

    A skill is active when its most recent event for its skill_id has
    op="activate" and status="active".  A rollback event (op="deactivate")
    removes it from the active set.
    """
    skills = [s for s in ledger.read(config, "skills")
              if s.get("agent_id") == agent.id]
    latest: Dict[str, Dict[str, Any]] = {}
    for s in skills:
        sid = s.get("skill_id", "")
        if sid:
            latest[sid] = s  # last write wins (ledger is append-only, chronological)
    return [s for s in latest.values() if s.get("status") == "active"]


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

    contradicted: List[Dict[str, Any]] = []
    for fp, group in failure_groups.items():
        if len(group) >= MIN_SUPPORT_FOR_CANDIDATE:
            qualifying_error_groups.append((fp, len(group)))
            rec = _propose_semantic_candidate(config, agent, group)
            if rec is None:
                skipped += 1                 # the write itself failed
            elif rec.get("contradicts"):
                # Proposed and recorded — it is evidence, and evidence that
                # argues with something already believed is the MOST worth
                # keeping. What it is not is promotable: `semantic.promote()`
                # refuses while the other entry is still active. Counted here
                # so the report stops implying nothing was in dispute.
                contradicted.append(rec)
                skipped += 1
            else:
                semantic_candidates.append(rec)

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
        "contradicted_candidates": contradicted,
        "skill_candidates": skill_candidates,
        "skipped_contradictions": skipped,
        "agent_id": agent.id,
    }
