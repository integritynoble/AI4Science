"""`WHY` — "why are you doing this?", answered from the record.

Three things the system already knew and never showed together: the goal, the
criteria a verdict will be judged against, and what the last verdict actually
said. Assembling them took three commands and the owner's memory of which
number came from where.

This is the command reached for when the others are not trusted, so **it reports
and never infers.** A plausible-sounding answer here is worse than a short one:

  * **there is no "current phase" in the answer.** Phase completion is tracked
    nowhere — the kickoff line says "earliest incomplete phase" and hands over
    `phases[0]` every time, on every steer, regardless of what has been done.
    Repeating that as progress would invent the one number the owner is asking
    about. `why` names the phase the session was *pointed at* and says the
    progress is not recorded.
  * **"not judged yet" is not "in progress".** No verdict is its own state.
  * **a stale plan says its criteria are no longer the standard**, because that
    is the single case where the criteria it just listed will not be applied.
"""
from __future__ import annotations

from typing import List

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config


def explain(config: Config, agent: Agent, task: tsk.Task) -> str:
    lines: List[str] = [f"{task.id} — {task.goal}", f"state: {task.state}"]

    plan = tsk.read_plan(config, agent, task)
    if plan is None or not plan.phases:
        lines.append("plan: no plan yet — nothing has been written to judge "
                     "this against.")
    else:
        lines.append(f"plan: {task.plan_version}.md, {len(plan.phases)} phase(s)")
        lines.append("  it was pointed at: " + plan.phases[0].title)
        # The honest part. `phases[0]` is what the kickoff and every steer hand
        # over, so calling it "current" would report a hardcode as progress.
        lines.append("  (which phase is finished is not tracked — the session "
                     "is pointed at the first one every time)")

    criteria = list(task.criteria or [])
    if task.plan_stale:
        lines.append("judged against: nothing — the plan is STALE. You drove "
                     "this session by hand, so its criteria are no longer the "
                     "standard, and `check` will refuse until the plan is "
                     "rewritten.")
    elif criteria:
        lines.append("judged against:")
        lines.extend(f"  {i}. {c}" for i, c in enumerate(criteria, start=1))
    else:
        lines.append("judged against: nothing recorded — there is no criterion "
                     "to meet.")

    verdict = task.verdict or {}
    state = verdict.get("state") or verdict.get("verdict")
    if not state:
        lines.append("verdict: it has not been judged yet.")
    else:
        reason = verdict.get("why") or verdict.get("reason") or "no reason given"
        lines.append(f"verdict: {state} — {reason}")
        if verdict.get("engine") and not verdict.get("independent", False):
            lines.append(f"  judged by {verdict['engine']}, the same engine that "
                         f"ran the session — not an independent check")

    if task.retries:
        from ai4science.harness.agents.sarsi import retry as rty
        lines.append(f"handed back {task.retries} of {rty.MAX_RETRIES} times "
                     f"with the verifier's reason")

    if task.awaiting:
        lines.append("waiting on you to grant: " + ", ".join(task.awaiting))
    elif task.blocked_by:
        lines.append(f"not moving: {task.blocked_by}")

    name = (task.session or {}).get("name")
    if name:
        # Named so the answer can be checked rather than believed.
        lines.append(f"session: {name} — see it yourself: tmux attach -t {name}")
        if task.steering_paused:
            lines.append("  you have the wheel; the worker is standing by")
        else:
            lines.append(f"  {agent.id} is steering it")
    else:
        lines.append("session: not started")

    return "\n".join(lines)
