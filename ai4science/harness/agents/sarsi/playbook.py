"""The playbook — the parameters an agent runs on, and the only way they change.

Recursive self-improvement here is one governed shape:

    propose  →  evidence-based rationale  →  **the owner signs**  →  adopt

Never a silent change; never a self-promotion. Three things are structurally
impossible rather than discouraged:

  * **an agent cannot promote its own candidate.** `sign(by_owner=False)` raises.
  * **authority is not tunable.** A candidate touching the ceiling, standing
    grants, or any other authority raises — an agent that could propose its own
    ceiling and be signed once would have found a path to widening itself.
  * **a parameter nothing reads cannot be introduced.** `TUNABLE` and
    `CONSUMED_BY` are checked against each other by a test, because a playbook
    full of numbers nothing consumes is theatre that reads as governance.

When no metric justifies a change, the honest candidate is **no change**, and it
says so rather than inventing an improvement to look busy.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

#: What may be tuned, and what actually reads it. Kept side by side on purpose.
CONSUMED_BY = {
    "max_concurrent_tasks": "task.start — how many sessions this worker runs at once",
    "verify_evidence_chars": "session.verify — how much screen is handed to the verifier",
    "digest_items": "the daily digest — how many items one read contains",
}
TUNABLE = tuple(CONSUMED_BY)

#: Never tunable, at any version, by any signature short of editing the registry.
AUTHORITY = ("ceiling", "standing_grants", "role", "self_aware", "rsi")

DEFAULTS = {"max_concurrent_tasks": 3, "verify_evidence_chars": 4000,
            "digest_items": 12}


class OwnerMustSign(Exception):
    """Only the owner promotes. The agent asked to promote itself."""


class NotTunable(Exception):
    """The candidate reached for something a playbook may not change."""


@dataclass
class Candidate:
    change: Optional[Dict[str, Any]]
    rationale: str


@dataclass
class Signature:
    adopted: bool
    version: int
    note: str = ""


# ── the book ──────────────────────────────────────────────────────────

def read(config: Config, agent: Agent) -> Dict[str, Any]:
    path = agent.playbook
    if not path.exists():
        book = {"version": 1, "params": dict(DEFAULTS), "candidate": None}
        book["params"]["max_concurrent_tasks"] = agent.max_concurrent_tasks
        _save(agent, book)
        return book
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"version": 1, "params": dict(DEFAULTS), "candidate": None}


def write(config: Config, agent: Agent, params: Dict[str, Any], *,
          version: Optional[int] = None) -> Dict[str, Any]:
    book = read(config, agent)
    book["params"].update(params)
    if version is not None:
        book["version"] = int(version)
    _save(agent, book)
    return book


def param(config: Config, agent: Agent, name: str) -> Any:
    return read(config, agent)["params"].get(name, DEFAULTS.get(name))


# ── propose ───────────────────────────────────────────────────────────

def propose(config: Config, agent: Agent, *, evidence: Dict[str, Any],
            change: Optional[Dict[str, Any]] = None,
            now: Callable[[], float] = time.time) -> Candidate:
    """Write a candidate from this agent's own measurements.

    Supplying `change` explicitly is how a caller (or a model) offers one; it is
    validated the same way, because the validation is the point.
    """
    if change is not None:
        _validate(change)
        candidate = Candidate(change=dict(change),
                              rationale=f"proposed directly: {change}")
    else:
        candidate = _from_evidence(config, agent, evidence)

    book = read(config, agent)
    book["candidate"] = ({"change": candidate.change,
                          "rationale": candidate.rationale,
                          "at": now()} if candidate.change else None)
    _save(agent, book)
    return candidate


def _from_evidence(config: Config, agent: Agent, evidence: Dict[str, Any]) -> Candidate:
    blocked = int(evidence.get("blocked_by_concurrency") or 0)
    refused = int(evidence.get("refused") or 0)
    verified = int(evidence.get("verified") or 0)
    current = read(config, agent)["params"]

    if blocked >= 3:
        proposed = int(current.get("max_concurrent_tasks", 3)) + 1
        return Candidate(
            change={"max_concurrent_tasks": proposed},
            rationale=(f"{blocked} task(s) sat blocked on concurrency while "
                       f"{verified} verified and {refused} were refused — "
                       f"raise max_concurrent_tasks to {proposed}"))
    if refused > verified and refused >= 3:
        proposed = max(1, int(current.get("max_concurrent_tasks", 3)) - 1)
        return Candidate(
            change={"max_concurrent_tasks": proposed},
            rationale=(f"{refused} refusals against {verified} verified — "
                       f"take on less at once, down to {proposed}"))
    # The honest outcome when nothing measured justifies a change.
    return Candidate(change=None,
                     rationale=("no change: nothing measured justifies one "
                                f"(blocked {blocked}, verified {verified}, "
                                f"refused {refused})"))


def _validate(change: Dict[str, Any]) -> None:
    for key in change:
        if key in AUTHORITY:
            raise NotTunable(
                f"{key!r} is authority, not a parameter — an agent may never "
                f"widen its own reach, and a ceiling it could propose and have "
                f"signed once would be exactly that")
        if key not in TUNABLE:
            raise NotTunable(f"unknown parameter {key!r}: nothing reads it, and "
                             f"a number nothing consumes only looks like a policy")


# ── sign ──────────────────────────────────────────────────────────────

def sign(config: Config, agent: Agent, *, by_owner: bool) -> Signature:
    if not by_owner:
        raise OwnerMustSign(
            f"{agent.id} cannot promote its own candidate; the only path to "
            f"adoption is the owner's signature")
    book = read(config, agent)
    candidate = book.get("candidate")
    if not candidate or not candidate.get("change"):
        # a signature with nothing pending is a no-op, not an accident
        return Signature(adopted=False, version=int(book["version"]),
                         note="nothing was pending")
    _validate(candidate["change"])
    book["params"].update(candidate["change"])
    book["version"] = int(book["version"]) + 1
    book["candidate"] = None
    _save(agent, book)
    return Signature(adopted=True, version=book["version"],
                     note=candidate.get("rationale", ""))


def discard(config: Config, agent: Agent) -> None:
    book = read(config, agent)
    book["candidate"] = None
    _save(agent, book)


def pending(config: Config, agent: Agent) -> Optional[Dict[str, Any]]:
    return read(config, agent).get("candidate")


def _save(agent: Agent, book: Dict[str, Any]) -> None:
    agent.playbook.parent.mkdir(parents=True, exist_ok=True)
    agent.playbook.write_text(json.dumps(book, indent=2, sort_keys=True))
