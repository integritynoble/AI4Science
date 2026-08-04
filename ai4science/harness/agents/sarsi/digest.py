"""`DIG` — one read across everything an agent did, instead of many.

`social` and `abraham` are marked `digest` in the roster: the owner asked for a
daily read rather than a running commentary. Nothing compiled one, so that
choice existed in the registry and nowhere else.

The thing a digest must not become is **a second inbox**. It reports what
*happened*; what is still *waiting* belongs to `attention`. Restating it here
would give one obligation two homes, and each would look like the other's copy —
so this points at what waits and deliberately does not repeat it.

Three rules beyond that:

  * **the span is stated, not implied.** "Today" read at 2am covers a different
    stretch than the same word at 6pm, so it says *since when*.
  * **nothing to report and nothing readable are different answers.** A quiet
    day and an unreadable ledger both produce a short digest, and only one of
    them means the agent was quiet.
  * **delivering moves the line; reading does not.** Otherwise the first person
    to glance at it consumes it for everybody.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Agent, Config

MARK_NAME = "digest-delivered.json"

#: What the agent did on its own authority — the same set `decisions` counts,
#: named here rather than imported so the two cannot drift apart silently.
_DECIDED = ("answered", "submitted", "steered", "answered-question", "retried")


@dataclass
class Digest:
    agent_id: str = ""
    verified: int = 0
    decided: int = 0
    outward: int = 0
    stopped: int = 0
    waiting: int = 0
    since: str = ""
    readable: bool = True

    @property
    def quiet(self) -> bool:
        return not (self.verified or self.decided or self.outward
                    or self.stopped)

    @property
    def text(self) -> str:
        if not self.readable:
            return (f"{self.agent_id}: its ledger could not be read, so what it "
                    f"did is unknown — this is not a quiet day, it is an "
                    f"unreadable one")
        span = f"since {self.since}" if self.since else "since it started"
        if self.quiet and not self.waiting:
            return f"{self.agent_id}: nothing happened {span}"

        parts: List[str] = []
        if self.verified:
            parts.append(f"{self.verified} verified")
        if self.decided:
            parts.append(f"{self.decided} decided without you")
        if self.outward:
            parts.append(f"{self.outward} left the machine")
        if self.stopped:
            parts.append(f"{self.stopped} stopped")
        head = (f"{self.agent_id} {span}: " + ", ".join(parts)) if parts else \
               f"{self.agent_id}: nothing happened {span}"
        if self.waiting:
            # pointed at, never restated: one obligation, one home
            head += (f"\n  {self.waiting} thing(s) still wait on you — "
                     f"`sarsi attention --agent {self.agent_id}` has them")
        return head


def _mark_path(agent: Agent):
    return agent.agent_dir / MARK_NAME


def _mark(agent: Agent) -> dict:
    """How many of this agent's entries had been seen at the last delivery.

    COUNTS, not a timestamp — the ledger stamps to the second, so anything
    recorded in the same second as the delivery compares equal and would be
    swallowed. `decisions` learned this the same way; repeating the timestamp
    version here would have lost a whole second of every digest, silently.
    """
    try:
        raw = json.loads(_mark_path(agent).read_text())
        return {"reports": int(raw.get("reports") or 0),
                "outward": int(raw.get("outward") or 0),
                "at": str(raw.get("at") or "")}
    except Exception:
        return {"reports": 0, "outward": 0, "at": ""}


def deliver(config: Config, agent: Agent, *, now=time.time) -> Digest:
    """Compile it and move the line. The line moves only here."""
    out = compile(config, agent)
    seen = _counts(config, agent)
    path = _mark_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**seen, "at": ledger._iso(now())},
                               indent=2) + "\n")
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return out


def compile(config: Config, agent: Agent) -> Digest:
    """What this agent did since the last delivery. Reading changes nothing."""
    mark = _mark(agent)
    out = Digest(agent_id=agent.id, since=mark["at"])

    try:
        reports = _mine(ledger.read(config, "reports"), agent)
        outward = _mine(ledger.read(config, "outward"), agent)
    except Exception:
        # Unreadable is its own answer. Reporting zero here would call an
        # unreadable ledger a quiet day.
        out.readable = False
        return out

    for entry in reports[mark["reports"]:]:
        state = str(entry.get("state") or "")
        if state == "verified":
            out.verified += 1
        elif state in _DECIDED:
            out.decided += 1
        elif state == "over-budget":
            out.stopped += 1

    from ai4science.harness.agents.sarsi import undo
    for entry in outward[mark["outward"]:]:
        if str(entry.get("outcome") or "") in undo.LEFT:
            out.outward += 1

    # counted from the live view, not from the period: something raised
    # yesterday and still open is still waiting on the owner today
    from ai4science.harness.agents.sarsi import questions as qst
    out.waiting = len(qst.open_of(config, agent))
    return out


def _mine(entries, agent: Agent) -> List[dict]:
    return [e for e in entries if e.get("agent") == agent.id]


def _counts(config: Config, agent: Agent) -> dict:
    try:
        return {"reports": len(_mine(ledger.read(config, "reports"), agent)),
                "outward": len(_mine(ledger.read(config, "outward"), agent))}
    except Exception:
        return {"reports": 0, "outward": 0}


def across(config: Config) -> List[Digest]:
    """One per worker. The manager holds no tasks and does nothing to report."""
    return [compile(config, agent) for agent in config.workers()]


def due(config: Config) -> List[Agent]:
    """The agents whose roster entry asked for a daily read.

    The flag says who gets one UNPROMPTED. Asking for any agent's digest is
    always allowed — refusing to answer a direct question about an agent
    because of a delivery preference would be absurd.
    """
    return [a for a in config.workers() if a.digest]
