"""`RLY` — one worker handing finished work to another.

`work` produces the benchmark numbers; `funding` needs them for an application.
Dependencies already let the **owner** order those two. What was missing is the
worker that finishes something noticing the next step and saying so.

Everything here turns on one refusal: **a worker may not give another worker
work.** An agent assigning to an agent with no owner in the loop is "a worker
that starts work on its own" wearing a second name, and that is on both source
documents' do-not-build list. So a handoff is a *proposal* — the same propose /
hold / sign shape the house rules use, for the same reason.

Four rules beyond that:

  * **you may only hand on what you finished.** A handoff from an unverified
    task delegates unfinished business, and the receiving worker would build on
    a claim rather than a result.
  * **the evidence travels as a link, not a summary.** The accepted task
    *depends on* the source, so the next worker reads what was actually verified
    rather than what the previous one said about it — and because the source is
    verified, the dependency is already satisfied and it can start.
  * **not to itself, and not to the manager.** One is just another task; the
    other drives nothing, so handing it work hands work to nobody.
  * **the reason travels.** The owner is deciding whether this really is the
    next step, and "work suggested it" is not a reason.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai4science.harness.agents.sarsi import plan as pl, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config
from ai4science.harness.agents.sarsi.worker import Directive, NotAWorker

PENDING_NAME = "HANDOFF.pending.json"
MAX_CHARS = 2000


class NotFinished(Exception):
    """Only verified work may be handed on."""


class OwnerMustAccept(Exception):
    """An agent may not accept work on the owner's behalf."""


def _path(agent: Agent) -> Path:
    return agent.agent_dir / PENDING_NAME


def pending(config: Config, agent: Agent):
    """The handoff waiting on the owner for this worker, or None."""
    try:
        raw = json.loads(_path(agent).read_text())
    except Exception:
        return None
    return raw if raw.get("goal") else None


def propose(config: Config, agent: Agent, source: tsk.Task, *, to: str,
            goal: str, because: str, now=time.time) -> dict:
    """Hand finished work on. It creates nothing — the owner accepts."""
    text = (goal or "").strip()
    reason = (because or "").strip()
    if not text:
        raise ValueError("a handoff with no goal is not a handoff")
    if not reason:
        raise ValueError(
            "a handoff has to say why this is the next step — the owner is "
            "deciding, and 'it suggested it' is not a reason")

    if to == agent.id:
        raise ValueError(
            f"{agent.id} cannot hand work to itself; that is just another task")
    recipient = config.agents.get(to)
    if recipient is None:
        raise KeyError(f"no agent {to!r} — known: {', '.join(sorted(config.agents))}")
    if not recipient.is_worker:
        raise NotAWorker(
            f"{to} drives no sessions, so handing it work hands work to nobody")

    verdict = source.verdict or {}
    if source.state != tsk.VERIFIED and \
            str(verdict.get("state") or "").upper() != "PASS":
        raise NotFinished(
            f"{source.id} is {source.state} and has no PASS — handing it on "
            f"would have {to} build on a claim rather than a result")

    record = {"from_agent": agent.id, "from_task": source.id,
              "from_goal": source.goal[:MAX_CHARS],
              "goal": text[:MAX_CHARS], "because": reason[:MAX_CHARS],
              "at": _stamp(now)}
    path = _path(recipient)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return record


def accept(config: Config, agent: Agent, *, by_owner: bool,
           now=time.time) -> Optional[tsk.Task]:
    """Create the handed-on task. Only the owner may."""
    if not by_owner:
        raise OwnerMustAccept(
            f"only you can accept work for {agent.id}; an agent accepting on "
            f"your behalf is an agent assigning work to an agent")
    held = pending(config, agent)
    if held is None:
        return None

    directive = Directive(agent_id=agent.id, goal=held["goal"])
    draft = pl.draft(directive)
    from dataclasses import replace
    # A LINK, not a summary: the next worker reads what was actually verified.
    # The source has a PASS, so this dependency is already satisfied and the
    # task can start — it records provenance without holding anything up.
    draft = replace(draft,
                    depends_on=[f"{held['from_agent']}/{held['from_task']}"])
    made = tsk.attach_plan(config, agent, tsk.create(config, agent, directive),
                           draft)
    decline(config, agent)
    return made


def decline(config: Config, agent: Agent) -> None:
    try:
        _path(agent).unlink()
    except OSError:
        pass


def _stamp(now) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(now(), timezone.utc).isoformat(
        timespec="seconds")
