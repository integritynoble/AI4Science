"""`BDG` — a declared ceiling on steps and elapsed time.

A session that has lost the thread does not announce it. It keeps working, and
the only thing that ends it is somebody looking — one live task burned about
eight minutes of unattended waiting and nothing noticed.

Four rules, and the first two are about what a budget must *not* do:

  * **it pauses, it does not fail.** Running out of budget says nothing about
    whether the work was right, so the task stops with its plan, its history and
    its verdict intact, and raising the budget resumes it. A `FAIL` here would
    record a judgment nobody made.
  * **unknown is not over.** Steps are counted from the session transcript. When
    that cannot be read the step budget is simply not enforced — stopping real
    work on the strength of a number nobody could read is worse than the overrun
    it was meant to prevent. Time is always measurable from the session's own
    start stamp, so the clock still bites.
  * **there is no default.** A default budget either kills legitimate long work
    or is so loose it never fires, and both teach the owner to ignore it.
  * **it is checked before the loop acts.** A budget enforced after the next
    step has already run is one step too late, every time.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config


@dataclass
class Status:
    over: bool = False
    why: str = ""
    steps: Optional[int] = None
    minutes: Optional[float] = None
    steps_known: bool = True
    minutes_known: bool = True

    def __bool__(self) -> bool:
        return self.over


def check(config: Config, agent: Agent, task: tsk.Task, *,
          acts: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
          now=time.time) -> Status:
    """Is this task past what its plan declared?"""
    out = Status()
    max_steps = task.max_steps
    max_minutes = task.max_minutes
    if not max_steps and not max_minutes:
        return out                       # nothing declared, nothing to enforce

    session = task.session or {}

    # ── the clock, which is always readable ───────────────────────────
    started = session.get("started_at")
    if max_minutes:
        if not started:
            out.minutes_known = False
        else:
            out.minutes = (float(now()) - float(started)) / 60.0
            if out.minutes > float(max_minutes):
                out.over = True
                out.why = (f"{out.minutes:.0f} minutes is past the "
                           f"{max_minutes} this plan declared")
                return out

    # ── the steps, which may not be ───────────────────────────────────
    if max_steps:
        cwd = session.get("cwd")
        if not cwd:
            out.steps_known = False
            return out
        from ai4science.harness.agents.sarsi import blast
        try:
            out.steps = len((acts or blast.acts_of)(cwd))
        except Exception:
            # Not "over". A number nobody could read must not stop real work.
            out.steps_known = False
            return out
        if out.steps > int(max_steps):
            out.over = True
            out.why = (f"{out.steps} steps is past the {max_steps} this plan "
                       f"declared")
    return out


def enforce(config: Config, agent: Agent, task: tsk.Task, *,
            acts: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
            runtime: Optional[Any] = None, now=time.time) -> tsk.Task:
    """Stop the task if it is past its budget. Otherwise change nothing."""
    status = check(config, agent, task, acts=acts, now=now)
    if not status.over:
        return task

    from ai4science.harness.agents.sarsi import session as ses

    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": "over-budget",
                   "ceiling": (task.session or {}).get("ceiling") or "unknown",
                   "evidence": [status.why]}, now=now)
    # Stopped, not failed: the plan and the history survive, and raising the
    # budget resumes it. No verdict is written — nobody judged the work.
    return ses.stop(config, agent, task, runtime=runtime, now=now)
