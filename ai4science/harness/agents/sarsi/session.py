"""`ASG` — the worker hands the plan to `sarsi-claude`, and takes the verdict back.

**This is the seam.** Below it the 27-node session loop runs unchanged; this
module owns only what sits above it:

  * **only a worker may assign.** The manager may tell a worker to work.
  * **the session is handed the PLAN, not the wish.** The kickoff names the plan
    file and the earliest incomplete phase, because the plan's `Verified when:`
    lines *are* the verifier's criteria — a session driven from the goal alone is
    judged against a standard the owner never reviewed.
  * **the kickoff does not carry the conversation.** What crosses is what the
    session needs; that is what keeps its context bounded independently of the
    chat's.
  * **one task, one session.** Stopping one task cannot disturb another.
  * **the verdict comes from a verifier.** There is no path from the worker to a
    PASS, and a verdict judged by the same engine that did the work says so
    rather than claiming an independence it does not have.

The runtime (tmux + Claude Code) and the verifier are injected, so every rule
above is testable without a terminal or a model.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from ai4science.harness.agents.sarsi import ledger, plan as pl, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config
from ai4science.harness.agents.sarsi.worker import NotAWorker

PASS = "PASS"
FAIL = "FAIL"


class NotReady(Exception):
    """The task is not ready to be assigned — and this says what it is waiting for."""


class CouldNotStart(Exception):
    """The session would not start. Reported, never pretended around."""


class MachineRuntime:
    """The real one: the machine agent's tmux session control."""

    def start(self, name: str, cwd: str, *, govern: bool, ceiling: str) -> Dict[str, Any]:
        from ai4science.harness.agents.machine import sessions
        return sessions.start_session(name, cwd, govern=govern, ceiling=ceiling)

    def send(self, name: str, text: str) -> Dict[str, Any]:
        from ai4science.harness.agents.machine import sessions
        return sessions.send_to_session(name, text)


def assign(config: Config, agent: Agent, task: tsk.Task, *,
           runtime: Optional[Any] = None, now=time.time) -> tsk.Task:
    if not agent.is_worker:
        raise NotAWorker(
            f"{agent.id} is a manager: assigning a task to sarsi-claude may be "
            f"performed only by a worker")
    if task.awaiting:
        raise NotReady("this task is still waiting on a grant: "
                       + ", ".join(task.awaiting))

    if task.session:
        return task                          # one task, one session

    runtime = runtime or MachineRuntime()
    workdir = tsk.dir_of(agent, task.id)
    workdir.mkdir(parents=True, exist_ok=True)
    name = f"{agent.id}-{task.id[-4:]}"

    started = runtime.start(name, str(workdir), govern=True, ceiling=agent.ceiling)
    if not (started or {}).get("ok"):
        reason = (started or {}).get("reason") or "the session would not start"
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "blocked",
                       "evidence": [reason]}, now=now)
        raise CouldNotStart(reason)

    task.session = {"name": started.get("name", name), "pid": started.get("pid"),
                    "cwd": str(workdir), "ceiling": agent.ceiling,
                    "engine": agent.model}
    task.state = tsk.RUNNING
    task = tsk._touch(agent, task, now)

    plan = tsk.read_plan(config, agent, task)
    runtime.send(task.session["name"], kickoff(task, plan))
    ledger.append(config, "directives",
                  {"agent": agent.id, "task": task.id, "assigned": True,
                   "session": task.session["name"], "goal": task.goal}, now=now)
    return task


def kickoff(task: tsk.Task, plan: Optional[pl.Plan]) -> str:
    """What the session is told first: the goal, its plan file, and the phase to
    work. Never the conversation that produced them."""
    lines = [f"Goal: {task.goal}"]
    if plan is not None and task.plan_version:
        lines.append(f"Your plan is {task.plan_version}.md in this folder. "
                     f"Work its earliest incomplete phase.")
        first = plan.phases[0]
        lines.append(f"Earliest incomplete phase: {first.title}")
        lines.append(f"Verified when: {first.verified_when}")
    lines.append("Report what you did with the evidence for it. "
                 "An independent verifier decides whether the goal is met.")
    return "\n".join(lines)


def verify(config: Config, agent: Agent, task: tsk.Task, *,
           verifier: Callable[..., Dict[str, Any]], evidence: str = "",
           engine: Optional[str] = None, runtime: Optional[Any] = None,
           now=time.time) -> tsk.Task:
    """Ask the verifier, and act on what it says.

    On PASS the task is verified and the verdict recorded. On FAIL the reason is
    **fed back into the session** as the next instruction rather than merely
    logged — a reason that only reaches a log steers nothing.
    """
    criteria = list(task.criteria or [])
    verdict = dict(verifier(goal=task.goal, criteria=criteria, evidence=evidence) or {})
    verdict["engine"] = engine or "unknown"
    # a different engine is the cheapest independence there is; when it is the
    # same one, say so rather than claiming an independence we do not have
    verdict["independent"] = bool(engine and engine != (agent.model or ""))
    verdict["criteria"] = criteria

    if str(verdict.get("state", "")).upper() == PASS:
        task = tsk.finish(config, agent, task, verdict=verdict, now=now)
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "verified",
                       "verdict": verdict, "evidence": [evidence[:500]]}, now=now)
        return task

    task.verdict = verdict
    task.state = tsk.RUNNING
    task = tsk._touch(agent, task, now)
    why = verdict.get("why") or "the verifier was not satisfied"
    steered = False
    if task.session:
        try:
            (runtime or MachineRuntime()).send(
                task.session["name"],
                f"The independent verifier says this is not done yet: {why}\n"
                f"Address that specifically, then report the evidence again.")
            steered = True
        except Exception:
            steered = False
    # A reason that reached no session steered nothing. Record that rather than
    # let the log imply a correction everyone assumes was delivered.
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": "running",
                   "verdict": verdict, "steered": steered,
                   "evidence": [evidence[:500]]}, now=now)
    return task


def answer(config: Config, agent: Agent, task: tsk.Task) -> str:
    """What the owner is told — **at what authority the claim stands.**

    In a fleet, "it worked" is an incomplete sentence.
    """
    session = (task.session or {}).get("name") or "no session"
    if task.state == tsk.VERIFIED and (task.verdict or {}).get("state") == PASS:
        independence = "" if (task.verdict or {}).get("independent") \
            else " (judged by the same engine that did the work)"
        return (f"verified — {task.goal}\n"
                f"session {session}, verdict {PASS}{independence}")
    if task.state == tsk.RUNNING:
        return f"recorded — {task.goal} is in progress in session {session}"
    return f"I think — {task.goal} is {task.state} in session {session}"
