"""`WHY` — "why are you doing this?", answered from the record.

Three things the system already knew and never showed together: the goal, the
criteria a verdict will be judged against, and what the last verdict actually
said. Assembling them took three commands and the owner's memory of which
number came from where.

This is the command reached for when the others are not trusted, so **it reports
and never infers.** A plausible-sounding answer here is worse than a short one:

  * **the phase it names is the one the verifier's record implies**, never a
    guess. A phase counts as done when a verdict says so *about that phase*;
    with no verdict it is "not judged yet", because silence is not success.
  * **"not judged yet" is not "in progress".** No verdict is its own state.
  * **a stale plan says its criteria are no longer the standard**, because that
    is the single case where the criteria it just listed will not be applied.
"""
from __future__ import annotations

from typing import List

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config


def explain(config: Config, agent: Agent, task: tsk.Task, *, acts=None) -> str:
    lines: List[str] = [f"{task.id} — {task.goal}", f"state: {task.state}"]

    plan = tsk.read_plan(config, agent, task)
    if plan is None or not plan.phases:
        lines.append("plan: no plan yet — nothing has been written to judge "
                     "this against.")
    else:
        lines.append(f"plan: {task.plan_version}.md, {len(plan.phases)} phase(s)")
        here = tsk.earliest_incomplete(task)
        criteria = list(task.criteria or [])
        for i, phase in enumerate(plan.phases):
            verdict = tsk.phase_verdict(task, i)
            if verdict:
                mark = f"{verdict.get('state', '?')} — {verdict.get('why', '')}"
            elif i == here:
                mark = "not judged yet — this is where the work is"
            else:
                mark = "not judged yet"
            lines.append(f"  {i + 1}. {phase.title}: {mark}")
            # the criterion beside the phase it judges, rather than in a second
            # numbered list the reader has to align by hand
            if i < len(criteria):
                lines.append(f"       verified when: {criteria[i]}")
        if here is None:
            lines.append("  every phase has its own PASS")

    criteria = list(task.criteria or [])
    if task.plan_stale:
        lines.append("judged against: nothing — the plan is STALE. You drove "
                     "this session by hand, so its criteria are no longer the "
                     "standard, and `check` will refuse until the plan is "
                     "rewritten.")
    elif not criteria:
        lines.append("judged against: nothing recorded — there is no criterion "
                     "to meet.")
    elif plan is None or not plan.phases:
        # No phase list to hang them off, so show them on their own.
        lines.append("judged against:")
        lines.extend(f"  {i}. {c}" for i, c in enumerate(criteria, start=1))

    verdict = task.verdict or {}
    state = verdict.get("state") or verdict.get("verdict")
    if not state:
        lines.append("verdict: it has not been judged yet.")
    else:
        reason = verdict.get("why") or verdict.get("reason") or "no reason given"
        if task.state == tsk.VERIFIED:
            lines.append(f"verdict: {state} — {reason}")
        elif verdict.get("phase"):
            # A phase verdict is NOT a task verdict. Printing it as one reads as
            # "this task passed" beside a task that has not.
            lines.append(f"last verdict (phase {verdict['phase']}): "
                         f"{state} — {reason}")
            lines.append("  the task itself is not verified — that needs every "
                         "phase")
        else:
            lines.append(f"last verdict: {state} — {reason}")
        engine = verdict.get("engine")
        if engine and engine != "unknown" and not verdict.get("independent"):
            lines.append(f"  judged by {engine}, the same engine that ran the "
                         f"session — not an independent check")

    if task.retries:
        from ai4science.harness.agents.sarsi import retry as rty
        lines.append(f"handed back {task.retries} of {rty.MAX_RETRIES} times "
                     f"with the verifier's reason")

    if task.awaiting:
        lines.append("waiting on you to grant: " + ", ".join(task.awaiting))
    elif task.blocked_by:
        lines.append(f"not moving: {task.blocked_by}")

    # what it wrote, against what it was allowed to write
    from ai4science.harness.agents.sarsi import blast
    radius = blast.check(config, agent, task, acts=acts)
    if radius.escaped:
        lines.append("BLAST RADIUS: wrote outside the declared paths — "
                     + ", ".join(radius.outside[:5]))
    elif radius.read and (radius.inside or radius.unchecked):
        lines.append("blast radius: " + radius.summary)

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
