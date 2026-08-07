"""One conversation with one agent — both roles, both doors.

Lives in that agent's `W_name`, so it is per agent name and never shared: what
you told `work` is not `abraham`'s to read.

**Records carry a `role`.** This was owner-only until the console session,
porting its chat door onto the canonical plane, pointed out that the agent's
reply was never written down anywhere in the plane: the gateway handed it to
the transport and dropped it, so Telegram lost its replies too and a chat door
could only ever render one side. The reply is recorded here now.

Adding a second role to a log that four other modules already read is the part
worth being careful about, so:

**`said()` returns the owner's turns only, and always has.** `composer`,
`answering` and `workspace` feed its result to the agent as *what the owner
told it*. If replies appeared there the agent would read its own words back as
instructions, and `already_said` would match on them and silently suppress a
genuine question — the exact failure its exact-match rule exists to prevent.
Call `transcript()` when you want both sides, which is what a chat door wants.

Records written before the field read as the owner's, because that is what they
were.

`already_said` is deliberately an **exact** match. A fuzzy one would suppress a
genuinely different question that merely read similarly, and silently not asking
for something the agent needs is worse than asking twice.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

LOG_NAME = "ownerlog.jsonl"
DEFAULT_LIMIT = 50

#: Who a record is from. An absent `role` is the owner's — that is what every
#: record written before this field existed was.
OWNER = "owner"
AGENT = "agent"


def append(config: Config, agent: Agent, text: str, *, surface: str,
           role: str = OWNER, delivered: Optional[bool] = None,
           mode: str = "",
           now: Callable[[], float] = time.time) -> Dict[str, Any]:
    """`mode` says HOW this reached the session — `guided` (the owner authored
    it), `worker-guided` (the worker did), `interact` (relayed verbatim).

    Two drivers share one session: most of the time the worker occupies the
    guide role and the owner joins occasionally. "The worker said this" and
    "the human said this" are different facts, and a history that merges them
    loses the one that matters.
    """
    record = {"text": text, "surface": surface, "role": role,
              "at": datetime.fromtimestamp(now(), timezone.utc).isoformat(timespec="seconds")}
    if mode:
        record["mode"] = mode
    if delivered is not None:
        # Only on a reply, and only when the surface can say. An owner's own
        # message has no delivery to report, and `None` is a third answer —
        # "nobody checked" — which must not read as "it did not arrive".
        record["delivered"] = bool(delivered)
    path = _path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return record


def reply(config: Config, agent: Agent, text: str, *, surface: str,
          delivered: Optional[bool] = None,
          now: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Record what the agent answered. Same log, other role.

    `delivered` says whether it reached the surface. A reply that was answered
    and never arrived reads identically to one that arrived, in the log the
    owner scrolls back through — and on Telegram they see nothing at all, which
    reads identically to an agent that had nothing to say. Two readers, two
    wrong pictures, in opposite directions.
    """
    return append(config, agent, text, surface=surface, role=AGENT,
                  delivered=delivered, now=now)


def role_of(record: Dict[str, Any]) -> str:
    """A record with no role is the owner's."""
    return record.get("role") or OWNER


def said(config: Config, agent: Agent, limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """What the **owner** said, most recent last. Bounded — the file is the
    history, this is a window over it.

    Owner-only on purpose: callers hand this to the agent as instruction. For
    both sides of the conversation use `transcript`."""
    return _read(agent, limit=limit, role=OWNER)


def transcript(config: Config, agent: Agent,
               limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """Both roles, oldest first — one conversation, however it was reached.

    A door that renders this shows the same exchange whether the owner typed it
    in Telegram or the console, which is what "two doors, one agent" means on
    screen. Read `role_of(record)` for the side; the `surface` says which door."""
    return _read(agent, limit=limit, role=None)


def already_said(config: Config, agent: Agent, text: str) -> bool:
    needle = (text or "").strip()
    return any((e.get("text") or "").strip() == needle
               for e in said(config, agent, limit=0))


def _read(agent: Agent, *, limit: int, role: Optional[str]) -> List[Dict[str, Any]]:
    path = _path(agent)
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if role is not None and role_of(record) != role:
            continue
        out.append(record)
    # Trim after filtering: a window of N owner turns should not shrink because
    # the agent happened to answer them.
    return out[-limit:] if limit else out


def _path(agent: Agent) -> Path:
    return agent.workspace / LOG_NAME
