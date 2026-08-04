"""`UND` — retracting the last outward act, and being straight about when it
cannot be done.

*"You approve a send, then regret it within a minute."* The outward ledger holds
enough to identify what left, so this can at least **try**. The design problem
is not the trying; it is refusing to let "I tried" read as "it is undone".

Most outward acts are not retractable, and saying so plainly is the feature:

  * **mail is gone.** SMTP handed it on and there is no recall. The only real
    remedy is a correction — a NEW outward act with its own approval — and
    calling that an undo would misdescribe what happened to the first one.
  * **a submitted form cannot be withdrawn.** `submit` already says so at the
    moment of asking; saying otherwise afterwards would make that warning a lie.
  * **a post may be deletable** — if the platform offers it and a handle was
    kept. That is the one case where retraction is real, and it is real only
    then.

Two more rules come from the ledger's own design. It stores a **digest and a
character count, never the body**, so this can say what left and to whom and
cannot reproduce it. And a retraction **leaves the machine too**, so it is
recorded as an outward act in its own right — a retraction nobody can audit is
the same problem as a send nobody can audit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Outcomes that mean it actually left. A refused or drafted act never did, so
#: there is nothing to retract.
LEFT = ("sent", "posted", "submitted", "delivered")

#: Kinds that cannot be taken back at all, and what to say instead.
IRREVERSIBLE = {
    "mail": ("mail cannot be recalled — SMTP handed it on and it is gone. "
             "The real remedy is a correction, which is a NEW outward act you "
             "must approve: `sarsi send {agent} --kind mail …`"),
    "form": ("a submitted form cannot be withdrawn. `submit` said so before you "
             "approved it; it would not be true to say otherwise now"),
    "recurring": ("a schedule you approved is not an act that left — stop it "
                  "with `sarsi vault policy`, which is where it lives"),
}


class NothingToUndo(Exception):
    """No outward act of this agent is outstanding."""


class Irreversible(Exception):
    """It left and it cannot be taken back. The message says what can be done."""


class Failed(Exception):
    """The retraction was attempted and did not succeed. Not 'undone'."""


@dataclass(frozen=True)
class Act:
    kind: str
    destination: str
    digest: str = ""
    chars: int = 0
    task_id: str = ""
    handle: str = ""
    at: str = ""

    def __str__(self) -> str:
        return (f"{self.kind} to {self.destination} ({self.chars} chars, "
                f"digest {self.digest[:12]}) at {self.at}")


def last(config: Config, agent: Agent) -> Optional[Act]:
    """The most recent act of this agent that actually left, and has not
    already been retracted."""
    try:
        entries = ledger.read(config, "outward")
    except Exception:
        return None

    # Only a SUCCESSFUL retraction closes an act. An attempt that failed left
    # the post published, so hiding it here would make the one command that
    # could take it down stop offering to — the failure reading as handled.
    retracted = {str(e.get("digest") or "") for e in entries
                 if e.get("agent") == agent.id and e.get("kind") == "retract"
                 and str(e.get("outcome") or "") == "retracted"}
    for entry in reversed(entries):
        if entry.get("agent") != agent.id:
            continue
        if entry.get("kind") == "retract":
            continue
        if str(entry.get("outcome") or "") not in LEFT:
            continue
        digest = str(entry.get("digest") or "")
        if digest and digest in retracted:
            continue
        return Act(kind=str(entry.get("kind") or ""),
                   destination=str(entry.get("destination") or ""),
                   digest=digest,
                   chars=int(entry.get("chars") or 0),
                   task_id=str(entry.get("task") or ""),
                   handle=str(entry.get("handle") or ""),
                   at=str(entry.get("at") or ""))
    return None


def retract(config: Config, agent: Agent, *,
            retractor: Optional[Callable[[Act], Any]] = None,
            now=time.time) -> Act:
    """Take back the last outward act, when that is a thing that can be done."""
    act = last(config, agent)
    if act is None:
        raise NothingToUndo(
            f"{agent.id} has nothing outstanding that left the machine")

    if act.kind in IRREVERSIBLE:
        raise Irreversible(IRREVERSIBLE[act.kind].format(agent=agent.id)
                           + f"\n  it was: {act}")

    if not act.handle:
        # Nothing identifies WHICH one to delete, and deleting the wrong post is
        # worse than deleting none.
        raise Irreversible(
            f"nothing identifies which {act.kind} to take back — no handle was "
            f"recorded when it was published, and deleting the wrong one is "
            f"worse than deleting none.\n  it was: {act}")

    if retractor is None:
        raise Irreversible(
            f"no way to retract a {act.kind} on {act.destination} is wired in "
            f"here. Take it down yourself; this will not pretend it did.\n"
            f"  it was: {act}")

    try:
        retractor(act)
    except Exception as e:
        # Recorded as an ATTEMPT, never as a retraction: an "undone" for
        # something still published is the worst possible entry in this ledger.
        ledger.append(config, "outward",
                      {"agent": agent.id, "task": act.task_id,
                       "kind": "retract", "destination": act.destination,
                       "digest": act.digest, "chars": 0,
                       "outcome": f"attempt-failed: {type(e).__name__}"},
                      now=now)
        raise Failed(f"the retraction was attempted and did not succeed: {e}. "
                     f"It is still published.")

    ledger.append(config, "outward",
                  {"agent": agent.id, "task": act.task_id, "kind": "retract",
                   "destination": act.destination, "digest": act.digest,
                   "chars": 0, "outcome": "retracted"}, now=now)
    return act
