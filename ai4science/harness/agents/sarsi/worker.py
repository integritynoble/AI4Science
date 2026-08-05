"""The worker plane — `DIR` down, `WK` admits, `CAP` checks, `REP` up.

Four rules live here, and each one is a refusal:

  * **a directive is a contract, not a conversation.** It carries goal, scope,
    criteria, budget, deadline and revocation — and a goal that has grown into a
    transcript is refused rather than truncated, because truncating loses the
    part the owner cared about without telling anyone.
  * **a worker is not commanded.** A directive is evidence that something is
    wanted; this worker decides whether it can be done *here*.
  * **nothing waits quietly.** A directive that cannot be placed is refused and
    reported in the same breath. An unplaceable directive that waits is
    indistinguishable, from the chat, from work in progress.
  * **a report may not claim success the verifier did not grant.** `verified`
    without a verdict raises; the worker does not grade its own work.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ai4science.harness.agents.sarsi import capability, ledger
from ai4science.harness.agents.sarsi.registry import Agent, Config

MAX_GOAL_CHARS = 2000
WAITING_STATES = ()          # deliberately empty: nothing here queues


class BadDirective(Exception):
    """The directive is not a contract. Refused at construction."""


class NotAWorker(Exception):
    """Only a worker touches sarsi-claude. The manager may not admit work."""


class UnverifiedClaim(Exception):
    """A report tried to claim a verdict no verifier gave."""


@dataclass
class Directive:
    agent_id: str
    goal: str
    scope: List[str] = field(default_factory=list)
    criteria: List[str] = field(default_factory=list)
    budget: Dict[str, Any] = field(default_factory=dict)
    deadline: Optional[str] = None
    revocation: Optional[str] = None
    requires_tools: List[str] = field(default_factory=list)
    requires_secrets: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"dir_{uuid.uuid4().hex[:10]}")

    def __post_init__(self) -> None:
        goal = (self.goal or "").strip()
        if not goal:
            raise BadDirective("a directive with no goal is not a contract")
        if len(goal) > MAX_GOAL_CHARS:
            raise BadDirective(
                f"the goal is {len(goal)} characters; a directive carries the "
                f"goal, not the conversation (limit {MAX_GOAL_CHARS}). Say what "
                f"the work is; the discussion stays in the chat.")
        self.goal = goal

    def as_record(self) -> Dict[str, Any]:
        return {"id": self.id, "agent": self.agent_id, "goal": self.goal,
                "scope": list(self.scope), "criteria": list(self.criteria),
                "budget": dict(self.budget), "deadline": self.deadline,
                "revocation": self.revocation,
                "requires_tools": list(self.requires_tools),
                "requires_secrets": list(self.requires_secrets)}


@dataclass
class Admission:
    admitted: bool
    directive: Directive
    reason: Optional[str] = None          # "capability" | "not-mine" | None
    missing: List[str] = field(default_factory=list)
    message: str = ""


def admit(config: Config, agent: Agent, directive: Directive, *,
          now=time.time, **probe_kw) -> Admission:
    if not agent.is_worker:
        raise NotAWorker(
            f"{agent.id} is a manager: it may tell a worker to work, and may "
            f"not admit work itself")
    if getattr(agent, "retired", False):
        # Refused by name rather than accepted: a task filed against a
        # retired agent is one nobody is going to supervise. Its record
        # stays readable — `tasks --archived`, `plan`, `blast`, `spend` all
        # still work — because retiring is about new work, not history.
        raise NotAWorker(
            f"{agent.id} is retired: it holds its history and takes no new "
            f"work. Hand this to sarsi-worker instead — its past tasks are "
            f"still readable with `sarsi tasks {agent.id} --archived`")

    if directive.agent_id != agent.id:
        out = Admission(False, directive, reason="not-mine",
                        message=f"this directive is addressed to "
                                f"{directive.agent_id!r}, not to {agent.id!r}")
        _record(config, agent, out, now=now)
        return out

    missing = capability.missing(config, agent, directive.requires_tools, **probe_kw) \
        if directive.requires_tools else []
    if missing:
        out = Admission(False, directive, reason="capability", missing=missing,
                        message=_nom(missing))
        _record(config, agent, out, now=now)
        return out

    out = Admission(True, directive, message="admitted")
    _record(config, agent, out, now=now)
    return out


def _nom(missing: Sequence[str]) -> str:
    """`NOM`: say what is missing, by name. Never 'I cannot do that'."""
    names = ", ".join(missing)
    return (f"nothing here can do this — {names} "
            f"{'is' if len(missing) == 1 else 'are'} not available on this machine")


def _record(config: Config, agent: Agent, out: Admission, *, now) -> None:
    record = out.directive.as_record()
    record.update({"admitted": out.admitted, "reason": out.reason,
                   "missing": list(out.missing)})
    ledger.append(config, "directives", record, now=now)
    if not out.admitted:
        # CAP → REP is automatic: the miss becomes an answer, not a silence.
        report(config, agent, out.directive, state="blocked",
               evidence=[out.message], needed_and_missing=list(out.missing), now=now)


def report(config: Config, agent: Agent, directive: Directive, *, state: str,
           evidence: Optional[Sequence[str]] = None,
           uncertainty: Optional[str] = None,
           needed_and_missing: Optional[Sequence[str]] = None,
           verdict: Optional[Dict[str, Any]] = None,
           extra: Optional[Dict[str, Any]] = None,
           now=time.time) -> Dict[str, Any]:
    if state == "verified" and not verdict:
        raise UnverifiedClaim(
            "a report may not claim `verified` without the verifier's verdict; "
            "the agent that did the work never grades it")
    record: Dict[str, Any] = {
        "directive": directive.id, "agent": agent.id, "state": state,
        "evidence": list(evidence or []), "uncertainty": uncertainty,
        "needed_and_missing": list(needed_and_missing or []),
        "verdict": verdict,
    }
    if extra:
        record.update(extra)          # ledger refuses it if it carries a secret
    return ledger.append(config, "reports", record, now=now)


def outstanding(config: Config, agent: Agent) -> List[Dict[str, Any]]:
    """Directives this worker admitted and has not yet reported on.

    A refused directive never appears here — that is what "not queued" means.
    """
    admitted = [d for d in ledger.read(config, "directives")
                if d.get("agent") == agent.id and d.get("admitted")]
    reported = {r.get("directive") for r in ledger.read(config, "reports")
                if r.get("agent") == agent.id}
    return [d for d in admitted if d.get("id") not in reported]
