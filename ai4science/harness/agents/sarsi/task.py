"""`TSK` — the unit a worker actually holds.

A worker is not a request handler. It holds **tasks**, several at once, each
with its own plan and (later) its own session, and it keeps holding them across
restarts.

Four properties, each of them a rule from the spec rather than a convenience:

  * **a task is visible from the moment it exists**, in whatever state it is in.
    A task the owner cannot see is a task the owner cannot stop.
  * **nothing is silently queued.** Over the concurrency limit a task stays
    `ready` and says `blocked_by = "concurrency"` — an unstarted task that looks
    like a running one is the `NOM` failure wearing a different hat.
  * **a task never disappears.** Turning one off keeps the record, which is what
    makes it resumable; a refusal is an outcome, not an error.
  * **`verified` is the verifier's word.** Finishing without a verdict raises.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field, replace as dataclasses_replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import plan as pl
from ai4science.harness.agents.sarsi.registry import Agent, Config
from ai4science.harness.agents.sarsi.worker import Directive, NotAWorker, UnverifiedClaim

RECORD_NAME = "task.json"

PLANNING = "planning"
AWAITING_GRANT = "awaiting-grant"
READY = "ready"
RUNNING = "running"
AWAITING_OWNER = "awaiting-owner"
VERIFIED = "verified"
OFF = "off"
REFUSED = "refused"
BLOCKED = "blocked"

#: states that occupy one of the worker's concurrency slots
ACTIVE_STATES = (RUNNING, AWAITING_OWNER)


@dataclass
class Task:
    id: str
    agent_id: str
    goal: str
    state: str = PLANNING
    directive: Dict[str, Any] = field(default_factory=dict)
    plan_version: Optional[str] = None
    criteria: List[str] = field(default_factory=list)
    awaiting: List[str] = field(default_factory=list)
    grants: List[str] = field(default_factory=list)
    blocked_by: Optional[str] = None
    verdict: Optional[Dict[str, Any]] = None
    session: Optional[Dict[str, Any]] = None
    #: the owner has the wheel — the worker must not type over them
    steering_paused: bool = False
    #: the plan no longer matches what is being done; its criteria are withheld
    plan_stale: bool = False
    #: the owner rewrote it; polish may propose a successor, never replace it
    plan_owner_edited: bool = False
    created_at: str = ""
    updated_at: str = ""


# ── creating and reading ──────────────────────────────────────────────

def create(config: Config, agent: Agent, directive: Directive, *,
           now=time.time) -> Task:
    _require_worker(agent)
    stamp = _iso(now())
    task = Task(id=f"tsk_{uuid.uuid4().hex[:10]}", agent_id=agent.id,
                goal=directive.goal, state=PLANNING,
                directive=directive.as_record(),
                created_at=stamp, updated_at=stamp)
    _save(agent, task)
    return task


def get(config: Config, agent: Agent, task_id: str) -> Optional[Task]:
    path = dir_of(agent, task_id) / RECORD_NAME
    if not path.exists():
        return None
    try:
        return Task(**json.loads(path.read_text()))
    except Exception:
        return None


def all_of(config: Config, agent: Agent) -> List[Task]:
    """Every task this agent holds, oldest first — including the ones that have
    not started, because those are exactly the ones a queue would hide."""
    out: List[Task] = []
    if not agent.tasks.exists():
        return out
    for child in sorted(agent.tasks.iterdir()):
        if child.is_dir():
            task = get(config, agent, child.name)
            if task is not None:
                out.append(task)
    return sorted(out, key=lambda t: t.created_at)


def dir_of(agent: Agent, task_id: str) -> Path:
    return agent.tasks / task_id


# ── the plan ──────────────────────────────────────────────────────────

def attach_plan(config: Config, agent: Agent, task: Task, plan: pl.Plan, *,
                now=time.time) -> Task:
    """Write `plan0.md` beside the task and take its criteria and permissions."""
    path = dir_of(agent, task.id) / f"{plan.version}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.render())
    task.plan_version = plan.version
    task.criteria = plan.criteria()
    task.awaiting = [p for p in plan.permissions if p not in task.grants]
    # asking here is the point of the plan step: the worst moment to request a
    # permission is halfway through unattended work
    task.state = AWAITING_GRANT if task.awaiting else READY
    return _touch(agent, task, now)


def read_plan(config: Config, agent: Agent, task: Task) -> Optional[pl.Plan]:
    if not task.plan_version:
        return None
    path = dir_of(agent, task.id) / f"{task.plan_version}.md"
    if not path.exists():
        return None
    parsed = pl.parse(path.read_text())
    # The markdown holds the content; the task record holds whether it is stale
    # and whether the owner rewrote it. Without this the flags are lost on every
    # read, and a polish round would quietly replace an owner-edited plan.
    return dataclasses_replace(parsed, version=task.plan_version,
                               stale=task.plan_stale,
                               owner_edited=task.plan_owner_edited)


# ── grants ────────────────────────────────────────────────────────────

def grant(config: Config, agent: Agent, task: Task, permission: str, *,
          now=time.time) -> Task:
    """Answer one declared permission. A grant answers what it names, no more."""
    if permission not in task.grants:
        task.grants.append(permission)
    task.awaiting = [p for p in task.awaiting if p != permission]
    if task.state == AWAITING_GRANT and not task.awaiting:
        task.state = READY
    return _touch(agent, task, now)


# ── the lifecycle ─────────────────────────────────────────────────────

def start(config: Config, agent: Agent, task: Task, *, now=time.time) -> Task:
    if task.awaiting:
        task.state = AWAITING_GRANT
        task.blocked_by = "grant"
        return _touch(agent, task, now)
    if task.state not in (READY, OFF):
        return task
    if _active_count(config, agent, exclude=task.id) >= max(1, agent.max_concurrent_tasks):
        # not a queue: it stays ready and says why, so the board never shows it
        # as though it were working
        task.state = READY
        task.blocked_by = "concurrency"
        return _touch(agent, task, now)
    task.state = RUNNING
    task.blocked_by = None
    return _touch(agent, task, now)


def finish(config: Config, agent: Agent, task: Task, *,
           verdict: Optional[Dict[str, Any]], now=time.time) -> Task:
    if not verdict:
        raise UnverifiedClaim(
            "a task may not be finished as verified without the verifier's "
            "verdict; the agent that did the work never grades it")
    task.verdict = dict(verdict)
    task.state = VERIFIED
    task.blocked_by = None
    return _touch(agent, task, now)


def turn_off(config: Config, agent: Agent, task: Task, *, now=time.time) -> Task:
    """Ends it, keeping the record — that is what makes it resumable."""
    task.state = OFF
    return _touch(agent, task, now)


def resume(config: Config, agent: Agent, task: Task, *, now=time.time) -> Task:
    task.state = READY
    return start(config, agent, task, now=now)


def refuse(config: Config, agent: Agent, task: Task, reason: str, *,
           now=time.time) -> Task:
    task.state = REFUSED
    task.blocked_by = reason
    return _touch(agent, task, now)


# ── internals ─────────────────────────────────────────────────────────

def _active_count(config: Config, agent: Agent, *, exclude: Optional[str] = None) -> int:
    return sum(1 for t in all_of(config, agent)
               if t.state in ACTIVE_STATES and t.id != exclude)


def _require_worker(agent: Agent) -> None:
    if not agent.is_worker:
        raise NotAWorker(f"{agent.id} is a manager: it holds no tasks and drives "
                         f"no sessions")


def _touch(agent: Agent, task: Task, now) -> Task:
    task.updated_at = _iso(now())
    _save(agent, task)
    return task


def _save(agent: Agent, task: Task) -> None:
    path = dir_of(agent, task.id) / RECORD_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(task), indent=2, sort_keys=True))


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")
