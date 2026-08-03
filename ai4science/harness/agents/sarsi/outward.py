"""`OWN` — the only way out of the machine.

> **Drafting is not sending.** An agent may compose anything. Every act that
> leaves the machine and reaches a person — an email, a post, a submission, a
> payment — requires an owner grant naming *that act*.

What this module refuses to do is the point of it:

| It will not | Because |
|---|---|
| transmit anything the owner did not see in full | an approval of a summary is not an approval of the message |
| transmit bytes other than the approved ones | no silent reformatting between approval and publication |
| treat a timeout, an error or a shrug as a yes | the absence of a refusal is not consent |
| carry one approval to a second act | one approval covers one act |
| batch unrelated acts into one question | so does batching |
| let repeated approvals become a standing grant | that is the agent granting itself authority by persistence |
| ask about a **reserved class** it cannot be granted | asking implies a grant would help, and none would |

The four reserved classes — `money`, `consent`, `publishing`, `legal` — no
ceiling grants at any tier. An agent holding no standing authority **abstains**
on them: it may prepare all four and complete none, which is correct rather
than a defect.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Agent, Config

GRANTS_NAME = "outward-grants.json"

#: The four classes **no ceiling** grants at any tier. An agent holding no
#: standing authority abstains on all of them — it may prepare and not complete.
MONEY = {"pay", "charge", "transfer", "subscribe"}
CONSENT = {"consent", "agree", "accept-terms"}
PUBLISHING = {"publish", "post"}
LEGAL = {"sign", "contract"}
RESERVED = MONEY | CONSENT | PUBLISHING | LEGAL

#: What a *ceiling* never grants is not the same as what the **owner** may grant
#: explicitly. The owner may write a bounded standing grant for publishing —
#: *"post to Substack, five times"* — and may not for the other three:
#:   * money needs the vault's grammar (limit + counterparty + rate), never a
#:     bare use count, or "five payments, to anyone" becomes writable;
#:   * agreeing on someone's behalf and signing are not classes you
#:     pre-authorise in bulk.
NO_BULK_GRANT = MONEY | CONSENT | LEGAL


class NotWhatWasApproved(Exception):
    """The bytes that went out were not the bytes that were approved."""


class Reserved(Exception):
    """A class no grant can authorise. It cannot be granted standing either."""


@dataclass(frozen=True)
class Act:
    agent_id: str
    kind: str                     # mail | post | submit | pay | …
    destination: str
    body: str
    task_id: str = ""
    #: what UNDOING costs and when that changes; None means unknown
    reversibility: Optional[Dict[str, Any]] = None

    def digest(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


@dataclass
class Outcome:
    approved: bool
    transmitted: bool = False
    abstained: bool = False
    reason: str = ""
    digest: str = ""


# ── drafting ──────────────────────────────────────────────────────────

def draft(config: Config, agent: Agent, act: Act, *, now=time.time) -> Outcome:
    """Compose without sending. Recorded, so a draft is never invisible."""
    _record(config, act, outcome="drafted", now=now)
    return Outcome(approved=False, reason="drafted — not sent", digest=act.digest())


# ── the gate ──────────────────────────────────────────────────────────

def request(config: Config, agent: Agent, act: Act, *,
            approve: Callable[..., Any], transmit: Callable[..., str],
            now=time.time) -> Outcome:
    """Show the owner exactly what would go out, and act only on a yes."""
    if not isinstance(act, Act):
        # batching unrelated acts into one approval is exactly what OWN forbids
        raise TypeError("OWN takes one act: one approval covers one act")

    if act.kind in RESERVED and not agent.standing_grants:
        reason = (f"{act.kind} is a reserved class — no grant could authorise "
                  f"it, so {agent.id} prepared it and stopped")
        _record(config, act, outcome="abstained", now=now)
        return Outcome(approved=False, abstained=True, reason=reason,
                       digest=act.digest())

    if _spend(config, act.agent_id, act.kind):
        return _transmit(config, act, transmit, via="standing grant", now=now)

    shown = render(act)
    try:
        answer = approve(act=act, shown=shown, reversibility=reversibility(act))
    except Exception as e:                      # an error is not consent
        _record(config, act, outcome="refused", now=now)
        return Outcome(approved=False, reason=f"could not ask you: {e}",
                       digest=act.digest())

    if not _is_yes(answer):
        # a refusal is an outcome, not an error
        _record(config, act, outcome="refused", now=now)
        return Outcome(approved=False, reason="you did not approve this",
                       digest=act.digest())

    # NOTE: nothing here writes a grant. A standing grant is `grant()`, an owner
    # act — never inferred from the fact that five drafts in a row were good.
    return _transmit(config, act, transmit, via="you approved this act", now=now)


def _transmit(config: Config, act: Act, transmit: Callable[..., str], *,
              via: str, now) -> Outcome:
    approved_body = act.body
    sent = transmit(act, body=approved_body)
    if sent is not None and sent != approved_body:
        # the approved bytes ARE the transmitted bytes
        _record(config, act, outcome="mismatch", now=now)
        raise NotWhatWasApproved(
            f"what went out is not what was approved for {act.destination}: "
            f"the transmitter changed it")
    _record(config, act, outcome="sent", now=now)
    return Outcome(approved=True, transmitted=True, reason=via, digest=act.digest())


def render(act: Act) -> str:
    """Exactly what will go out — recipient, destination, and the whole body."""
    return (f"{act.agent_id} wants to {act.kind}\n"
            f"to: {act.destination}\n"
            f"---\n{act.body}\n---")


def reversibility(act: Act) -> str:
    """What UNDOING costs, and when that changes.

    An approval showing only the price has asked about half the decision — and
    when nobody supplied the number, it must read as **unknown**, never as free.
    """
    r = act.reversibility or {}
    cost, until = r.get("cost"), r.get("until")
    if not cost:
        return "reversibility: unknown — nobody has supplied this"
    if until:
        return f"reversibility: free to undo until {until}, then {cost}"
    return f"reversibility: undoing costs {cost}"


# ── standing grants: bounded, spent, and never for a reserved class ───

def grant(config: Config, *, agent_id: str, kind: str, uses: int = 1) -> Dict[str, Any]:
    if kind in MONEY:
        raise Reserved(
            f"{kind} moves money: write it as a vault policy with a limit, a "
            f"counterparty class and a rate. A bare use count would say 'five "
            f"payments, to anyone'.")
    if kind in NO_BULK_GRANT:
        raise Reserved(
            f"{kind} is not a class you pre-authorise in bulk — agreeing on "
            f"someone's behalf, or signing, is decided one act at a time")
    grants = _read(config)
    record = {"agent": agent_id, "kind": kind, "uses": int(uses)}
    grants.append(record)
    _write(config, grants)
    return record


def grants(config: Config, agent_id: str) -> List[Dict[str, Any]]:
    return [g for g in _read(config) if g.get("agent") == agent_id]


def _spend(config: Config, agent_id: str, kind: str) -> bool:
    """Spend one use of a matching grant. A three-use grant really is three."""
    grants_all = _read(config)
    for g in grants_all:
        if g.get("agent") == agent_id and g.get("kind") == kind and int(g.get("uses", 0)) > 0:
            g["uses"] = int(g["uses"]) - 1
            _write(config, [x for x in grants_all if int(x.get("uses", 0)) > 0])
            return True
    return False


def _is_yes(answer: Any) -> bool:
    if answer is True:
        return True
    return str(answer or "").strip().lower() in {"y", "yes", "approve", "ok", "send"}


# ── the record ────────────────────────────────────────────────────────

def _record(config: Config, act: Act, *, outcome: str, now) -> None:
    # a digest, not the body: an outward draft can hold a salary expectation, a
    # medical detail, or someone else's address, and a ledger is not the place
    # for a second copy of it
    ledger.append(config, "outward",
                  {"agent": act.agent_id, "task": act.task_id, "kind": act.kind,
                   "destination": act.destination, "digest": act.digest(),
                   "chars": len(act.body), "outcome": outcome}, now=now)


def _path(config: Config) -> Path:
    return config.root / GRANTS_NAME


def _read(config: Config) -> List[Dict[str, Any]]:
    path = _path(config)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(config: Config, grants_all: List[Dict[str, Any]]) -> None:
    path = _path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(grants_all, indent=2, sort_keys=True))
    try:
        path.chmod(0o600)
    except Exception:
        pass
