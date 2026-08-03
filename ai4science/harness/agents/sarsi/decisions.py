"""`DEC` — what the agent decided without being asked.

At `A2` the supervision loop answers ordinary gates, submits stranded prompts,
composes steering, answers the session's questions and hands failures back. Each
of those is the agent exercising authority for one act rather than bringing it
to the owner. All of them were recorded and **none of them were ever read back**,
so the single figure that shows an agent over-reaching did not exist.

Four rules, three of which are about what must *not* be counted:

  * **only the agent's own acts.** A gate the owner answered is not a decision
    the agent made. Mixing the two inflates the number until it means nothing,
    and a number that means nothing is worse than none — it reads as oversight.
  * **the rung travels with the act.** Over-reach *is* a decision taken at a
    ceiling the agent should not have been at; without the rung the list cannot
    show the thing it exists for. An act recorded with no ceiling says
    `unknown`, never `A2` — guessing the rung is precisely the error being
    looked for.
  * **reading does not acknowledge.** An oversight tool whose second run shows
    nothing teaches the owner that nothing happened. Acknowledging is a separate
    and deliberate act.
  * **the total is always stated**, so acknowledging can hide nothing. It moves
    the line; it does not erase what is under it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Acts the AGENT took on its own authority. Each is one moment the owner was
#: not asked, and together they are the answer to "what did you do without me".
OWN_ACTS = {
    "answered": "answered a permission gate itself",
    "submitted": "submitted a prompt the session had left sitting",
    "steered": "composed and sent an instruction",
    "answered-question": "answered a question the session asked",
    "retried": "handed a failure back to the session",
}

#: Recorded, and deliberately NOT decisions: things the OWNER did, and things
#: the agent merely observed. Listed rather than filtered by omission, so a new
#: ledger state shows up as unclassified instead of silently counting.
OWNER_ACTS = {"guided-by-owner", "plan-rejected", "granted"}
OBSERVATIONS = {"gate", "blocked", "question", "verified", "unverified",
                "not-judged", "running", "planned", "failed", "briefing",
                "abstained", "guided"}

MARK_NAME = "decisions-read.json"


@dataclass(frozen=True)
class Decision:
    kind: str
    task_id: str
    detail: str
    ceiling: str = "unknown"
    at: str = ""
    agent_id: str = ""

    @property
    def what(self) -> str:
        return OWN_ACTS.get(self.kind, self.kind)

    def __str__(self) -> str:
        where = f"{self.agent_id}/{self.task_id}" if self.agent_id else self.task_id
        return f"[{self.ceiling}] {where} {self.what}: {self.detail}"


@dataclass
class Decisions:
    items: List[Decision] = field(default_factory=list)
    #: every one ever recorded, acknowledged or not
    total: int = 0

    @property
    def summary(self) -> str:
        if not self.items:
            return (f"nothing decided without you since you last acknowledged "
                    f"({self.total} in all)")
        by_rung: Dict[str, int] = {}
        for item in self.items:
            by_rung[item.ceiling] = by_rung.get(item.ceiling, 0) + 1
        rungs = ", ".join(f"{n} at {rung}"
                          for rung, n in sorted(by_rung.items(), reverse=True))
        return (f"{len(self.items)} decided without you: {rungs} "
                f"({self.total} in all)")


# ── reading them ──────────────────────────────────────────────────────

def _mark_path(agent: Agent):
    return agent.agent_dir / MARK_NAME


def _mark(agent: Agent) -> int:
    """How many decisions have been acknowledged.

    A **count**, not a timestamp. The ledger stamps to the second, so a decision
    taken in the same second as the acknowledgement compares equal and would be
    swallowed — silently, and exactly at the moment the owner had just looked
    away. Counting is exact at any clock resolution.
    """
    try:
        return int(json.loads(_mark_path(agent).read_text()).get("count") or 0)
    except Exception:
        return 0


def acknowledge(config: Config, agent: Agent, *, now=time.time) -> None:
    """Move the line. What is under it stays readable with `all_of`."""
    seen = len(_decisions(config, agent))
    path = _mark_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"count": seen, "at": ledger._iso(now())},
                               indent=2) + "\n")
    try:
        path.chmod(0o600)
    except Exception:
        pass


def all_of(config: Config, agent: Agent) -> Decisions:
    """Every decision this agent has taken on its own authority, ever."""
    rows = _decisions(config, agent)
    return Decisions(items=rows, total=len(rows))


def since(config: Config, agent: Agent) -> Decisions:
    """The ones taken since the owner last acknowledged.

    A mark larger than the list means the ledger has shrunk under it — rotated,
    or moved. Showing everything again would be noise; showing nothing is the
    safe reading, and the total still says what is there.
    """
    rows = _decisions(config, agent)
    return Decisions(items=rows[_mark(agent):], total=len(rows))


def across(config: Config) -> Decisions:
    """The fleet, named. The manager decides nothing — it drives nothing."""
    items: List[Decision] = []
    total = 0
    for agent in config.workers():
        got = since(config, agent)
        total += got.total
        items.extend(got.items)
    items.sort(key=lambda d: d.at)
    return Decisions(items=items, total=total)


def _decisions(config: Config, agent: Agent) -> List[Decision]:
    out: List[Decision] = []
    try:
        entries = ledger.read(config, "reports")
    except Exception:
        return out
    for entry in entries:
        if entry.get("agent") != agent.id:
            continue
        state = str(entry.get("state") or "")
        if state not in OWN_ACTS:
            continue
        evidence = entry.get("evidence") or []
        detail = str(evidence[0]) if evidence else ""
        out.append(Decision(
            kind=state,
            task_id=str(entry.get("task") or ""),
            detail=detail[:300],
            # never defaulted to A2: guessing the rung is the error this list
            # exists to catch
            ceiling=str(entry.get("ceiling") or "unknown"),
            at=str(entry.get("at") or ""),
            agent_id=agent.id))
    return out
