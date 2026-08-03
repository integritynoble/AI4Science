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

    #: what actually executes the session, for the independence comparison
    engine = "claude"

    def start(self, name: str, cwd: str, *, govern: bool, ceiling: str,
              env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        from ai4science.harness.agents.machine import sessions
        if env:
            # The secret reaches the local session and nothing that outlives it.
            import os
            os.environ.update({_env_key(k): v for k, v in env.items()})
        return sessions.start_session(name, cwd, govern=govern, ceiling=ceiling)

    def send(self, name: str, text: str) -> Dict[str, Any]:
        from ai4science.harness.agents.machine import sessions
        return sessions.send_to_session(name, text)


def assign(config: Config, agent: Agent, task: tsk.Task, *,
           runtime: Optional[Any] = None, vault_prompt: Optional[Callable] = None,
           now=time.time) -> tsk.Task:
    if not agent.is_worker:
        raise NotAWorker(
            f"{agent.id} is a manager: assigning a task to sarsi-claude may be "
            f"performed only by a worker")
    if task.awaiting:
        raise NotReady("this task is still waiting on a grant: "
                       + ", ".join(task.awaiting))

    if task.session:
        return task                          # one task, one session

    # VLT sits here: between the owner's grant and the session starting. A
    # denied secret stops the task before any session exists, and the denial
    # names the secret so the owner can grant it if they meant to.
    secrets = _unlock(config, agent, task, vault_prompt)

    runtime = runtime or MachineRuntime()
    workdir = tsk.dir_of(agent, task.id)
    workdir.mkdir(parents=True, exist_ok=True)
    name = f"{agent.id}-{task.id[-4:]}"

    started = runtime.start(name, str(workdir), govern=True, ceiling=agent.ceiling,
                            env=secrets)
    if not (started or {}).get("ok"):
        reason = (started or {}).get("reason") or "the session would not start"
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "blocked",
                       "evidence": [reason]}, now=now)
        raise CouldNotStart(reason)

    task.session = {"name": started.get("name", name), "pid": started.get("pid"),
                    "cwd": str(workdir), "ceiling": agent.ceiling,
                    # what ACTUALLY executes the session — the CLI the runtime
                    # drives. Independence is a claim about the engine that did
                    # the work, not the one the worker planned with.
                    "engine": getattr(runtime, "engine", "claude"),
                    "planner": agent.model}
    task.state = tsk.RUNNING
    task = tsk._touch(agent, task, now)

    plan = tsk.read_plan(config, agent, task)
    runtime.send(task.session["name"], kickoff(task, plan))
    ledger.append(config, "directives",
                  {"agent": agent.id, "task": task.id, "assigned": True,
                   "session": task.session["name"], "goal": task.goal}, now=now)
    return task


def _unlock(config: Config, agent: Agent, task: tsk.Task,
            prompt: Optional[Callable]) -> Dict[str, str]:
    """Ask the vault for every secret this task's directive declared.

    Returns the values for the local session only. They are never written to the
    task record, the plan, or any ledger — the vault ledger records *which*
    secret was asked for and what was decided, and nothing more.
    """
    from ai4science.harness.agents.sarsi import vault

    wanted = list((task.directive or {}).get("requires_secrets") or [])
    if not wanted:
        return {}
    prompt = prompt or _refuse_silently
    out: Dict[str, str] = {}
    for secret in wanted:
        decision = vault.ask(config, agent_id=agent.id, secret=secret,
                             act="read", purpose=task.goal, prompt=prompt,
                             standing_grants=agent.standing_grants)
        if not decision.allowed:
            raise NotReady(decision.reason)
        out[secret] = decision.value or ""
    return out


def _refuse_silently(**_: Any) -> None:
    """No way to reach the owner is not an approval."""
    return None


def _env_key(name: str) -> str:
    return name.upper().replace(".", "_").replace("-", "_")


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
    # A different engine is the cheapest independence there is; when it is the
    # same one, say so rather than claiming an independence we do not have.
    # Compared against the engine that RAN the session: the live run recorded
    # `independent: true` for a claude-judged, claude-executed task because the
    # worker's planning model happened to be a different string.
    ran_it = (task.session or {}).get("engine") or agent.model or ""
    verdict["independent"] = bool(engine and engine != ran_it)
    verdict["criteria"] = criteria

    from ai4science.harness.agents.sarsi import verifier as vf

    if not vf.was_judged(verdict):
        # Nothing judged this. It is not a pass, and it is not a finding about
        # the work either — so nothing is steered into the session. Telling it
        # to "address" an absent verifier is a correction nobody made about a
        # problem it cannot fix.
        task.verdict = verdict
        task.state = tsk.RUNNING
        task = tsk._touch(agent, task, now)
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "unverified",
                       "verdict": verdict, "steered": False,
                       "evidence": [evidence[:500]]}, now=now)
        return task

    if vf.is_pass(verdict):
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
    verdict = task.verdict or {}
    if str(verdict.get("state", "")).upper() == "UNVERIFIED":
        # distinct from "in progress": the work may be done and nobody looked
        return (f"not judged — {task.goal}\n"
                f"session {session}: {verdict.get('why', '')}")
    if task.state == tsk.RUNNING:
        return f"recorded — {task.goal} is in progress in session {session}"
    return f"I think — {task.goal} is {task.state} in session {session}"
