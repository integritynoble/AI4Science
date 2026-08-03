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
#: terminal. The record is kept — the plan, the verdict and the history are what
#: the agent actually did — but the slot is freed and it is off the default
#: board. Deleting is still not a thing a worker does.
ARCHIVED = "archived"

#: states that occupy one of the worker's concurrency slots
ACTIVE_STATES = (RUNNING, AWAITING_OWNER)


class Archived(Exception):
    """Raised rather than silently reviving a task the owner closed."""


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
    #: The first instruction this session is owed, held until it can receive
    #: it. Typing into a session that is still booting loses the text, and the
    #: worker then believes it has told the session something it never heard.
    kickoff_pending: Optional[str] = None
    #: how many times it has been typed without being seen to land
    kickoff_tries: int = 0
    #: it was typed repeatedly and never appeared. The owner is told rather than
    #: the loop typing forever.
    kickoff_undelivered: bool = False
    #: the last text `SP` pressed Enter on. Text still sitting at the prompt
    #: after that was never input — it is Claude Code's dimmed suggestion, which
    #: a captured pane renders identically to something typed.
    last_submitted: Optional[str] = None
    #: Sessions this task has already had. Kept so `spend` can still say what
    #: a stopped or archived task cost — the live record is cleared on stop,
    #: and the working directory it names is where the transcript lives.
    past_sessions: List[Dict[str, Any]] = field(default_factory=list)
    #: Paths besides the working directory this plan declared it may change.
    may_touch: List[str] = field(default_factory=list)
    #: Where the work happens, from the plan's `Working directory:` line.
    #: Evidence is gathered from here; empty means the task's own folder.
    work_root: Optional[str] = None
    #: Per-phase verdicts, keyed by phase index as a STRING (JSON has no int
    #: keys). A phase is complete when the verifier said so ABOUT THAT PHASE —
    #: not when the session claims it and not when the loop moves on. Without
    #: this, "earliest incomplete phase" was `phases[0]` forever.
    phase_verdicts: Dict[str, Any] = field(default_factory=dict)
    #: how many times the verifier's FAIL has been handed back to the session.
    #: Capped: a task that has failed this often wants the owner, not another
    #: attempt. Cleared by a PASS, so old failures do not follow a task that
    #: has since succeeded.
    retries: int = 0
    #: has this plan been settled between the worker and the session (or by the
    #: owner)? A worker's seed is a starting point, not an agreed plan, and the
    #: difference is whether the session has had its say.
    plan_agreed: bool = False
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


def all_of(config: Config, agent: Agent, *, archived: bool = False) -> List[Task]:
    """Every task this agent holds, oldest first — including the ones that have
    not started, because those are exactly the ones a queue would hide.

    Archived tasks are off this board by default and returned on their own with
    `archived=True`. Mixing them in would grow the board without bound until the
    live work was invisible inside the record of the finished work.
    """
    out: List[Task] = []
    if not agent.tasks.exists():
        return out
    for child in sorted(agent.tasks.iterdir()):
        if child.is_dir():
            task = get(config, agent, child.name)
            if task is None:
                continue
            if (task.state == ARCHIVED) == archived:
                out.append(task)
    return sorted(out, key=lambda t: t.created_at)


# ── phases ────────────────────────────────────────────────────────────

def phase_verdict(task: Task, index: int) -> Optional[Dict[str, Any]]:
    """The verdict recorded for one phase, or None if it has not been judged."""
    return (task.phase_verdicts or {}).get(str(index))


def phase_passed(task: Task, index: int) -> bool:
    verdict = phase_verdict(task, index)
    return str((verdict or {}).get("state", "")).upper() == "PASS"


def earliest_incomplete(task: Task) -> Optional[int]:
    """The first phase without a PASS, or None when every one has it.

    Counted over the task's CRITERIA, which is one per phase. A phase with no
    verdict is incomplete — silence is not success.
    """
    for index in range(len(task.criteria or [])):
        if not phase_passed(task, index):
            return index
    return None if task.criteria else 0


def record_phase(config: Config, agent: Agent, task: Task, index: int,
                 verdict: Dict[str, Any], *, now=time.time) -> Task:
    if index < 0 or index >= len(task.criteria or []):
        raise IndexError(
            f"{task.id} has {len(task.criteria or [])} phase(s); there is no "
            f"phase {index + 1}")
    task.phase_verdicts = dict(task.phase_verdicts or {})
    task.phase_verdicts[str(index)] = dict(verdict)
    return _touch(agent, task, now)


def clear_phase(task: Task, index: Optional[int] = None) -> Task:
    """Forget what was judged, because the standard it was judged against is
    gone. `index=None` clears every phase — for a plan that was re-drafted.

    Not persisted here: the caller is mid-edit and saves once, and a clear that
    wrote itself would race the edit that caused it.
    """
    current = dict(task.phase_verdicts or {})
    if index is None:
        current = {}
    else:
        current.pop(str(index), None)
    task.phase_verdicts = current
    return task


def evidence_root(agent: Agent, task: Task) -> Path:
    """Where this task's evidence is gathered from.

    The plan's declared `Working directory:` when it has one, the task's own
    folder otherwise. Declared, never inferred — a criterion naming a path does
    not move this, or "read /etc/passwd" would be a criterion away.
    """
    declared = (task.work_root or "").strip()
    if not declared:
        return dir_of(agent, task.id).resolve()
    try:
        return Path(declared).expanduser().resolve()
    except OSError:
        return dir_of(agent, task.id).resolve()


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
    task.work_root = plan.work_root
    task.may_touch = list(plan.may_touch)
    task.awaiting = [p for p in plan.permissions if p not in task.grants]
    # asking here is the point of the plan step: the worst moment to request a
    # permission is halfway through unattended work
    task.state = AWAITING_GRANT if task.awaiting else READY
    task.plan_agreed = False          # a seed: the session has not seen it yet
    return _touch(agent, task, now)


def adopt_plan(config: Config, agent: Agent, task: Task, plan: pl.Plan, *,
               now=time.time) -> Task:
    """Take a plan the SESSION wrote, without rewriting the file it wrote.

    `attach_plan` renders a plan the worker composed; this takes one that
    already exists on disk, so the session's own wording survives intact.
    """
    task.plan_version = plan.version
    task.criteria = plan.criteria()
    task.work_root = plan.work_root
    task.may_touch = list(plan.may_touch)
    task.awaiting = [p for p in plan.permissions if p not in task.grants]
    task.state = AWAITING_GRANT if task.awaiting else READY
    task.plan_agreed = True           # the session has had its say
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
    if _active_count(config, agent, exclude=task.id) >= max(1, _concurrency(config, agent)):
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
    # a run that succeeded should not carry its earlier failures forward
    task.retries = 0
    return _touch(agent, task, now)


def turn_off(config: Config, agent: Agent, task: Task, *, now=time.time) -> Task:
    """Ends it, keeping the record — that is what makes it resumable."""
    task.state = OFF
    return _touch(agent, task, now)


def archive(config: Config, agent: Agent, task: Task, *, now=time.time) -> Task:
    """Terminal: the record is kept, the slot is freed, the board is clear.

    Distinct from `turn_off`, which is resumable. Closing a task the owner meant
    to come back to, and closing one they are done with, are different acts and
    conflating them loses one of them.
    """
    task.state = ARCHIVED
    task.blocked_by = None
    return _touch(agent, task, now)


def resume(config: Config, agent: Agent, task: Task, *, now=time.time) -> Task:
    if task.state == ARCHIVED:
        raise Archived(f"{task.id} was archived; re-open it deliberately with "
                       f"`sarsi reopen` rather than resuming it by accident")
    task.state = READY
    return start(config, agent, task, now=now)


def reopen(config: Config, agent: Agent, task: Task, *, now=time.time) -> Task:
    """Put an archived task back on the board, stopped rather than running —
    the owner decides when it starts."""
    task.state = OFF
    return _touch(agent, task, now)


def refuse(config: Config, agent: Agent, task: Task, reason: str, *,
           now=time.time) -> Task:
    task.state = REFUSED
    task.blocked_by = reason
    return _touch(agent, task, now)


# ── internals ─────────────────────────────────────────────────────────

def _concurrency(config: Config, agent: Agent) -> int:
    """How many sessions this worker runs at once — from the **playbook**, which
    is the value the RSI loop tunes and the owner signs. The registry supplies
    the starting value; without reading it here, a promoted parameter would move
    on disk and change nothing."""
    from ai4science.harness.agents.sarsi import playbook as pb
    try:
        return int(pb.param(config, agent, "max_concurrent_tasks"))
    except Exception:
        return int(agent.max_concurrent_tasks)


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
