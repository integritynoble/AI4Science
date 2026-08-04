"""`HND` — what the next session needs, written before this one ends.

The task layout named `HANDOFF.md` and nothing wrote it, so a stopped and
resumed task began again from the plan alone: the next session could not tell
which phases were already verified, what the verifier had objected to, or what
the owner had been asked.

One rule shapes every line: **it records what the RECORD knows, not what the
session believed.** A handoff that says *"I was about to run the export"* is a
guess about a process that has ended, and a confident guess is exactly what
makes the next session redo the wrong half. Where the record is silent, so is
the file.

Three consequences:

  * **verified phases are named so they are not redone.** That is the whole
    point, and it became possible only when a phase started carrying its own
    verdict — before that, "which phases are done" had no answer to write down.
  * **no secret and no body.** Same rule as the ledger and the workspace: this
    file sits in the task folder, and a task folder is not a place for a second
    copy of a credential. Grants are named; their values are not read.
  * **a thin record makes a short file.** Padding it to look thorough would be
    inventing the very thing it exists to avoid.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

FILE_NAME = "HANDOFF.md"


def render(config: Config, agent: Agent, task: tsk.Task) -> str:
    """The handoff, as markdown. Only what the record actually holds."""
    lines: List[str] = [f"# Handoff — {task.id}", "",
                        f"**Goal:** {task.goal}", ""]

    plan = tsk.read_plan(config, agent, task)
    if plan is not None and plan.phases:
        done = [p.title for i, p in enumerate(plan.phases)
                if tsk.phase_passed(task, i)]
        if done:
            lines += ["## Already verified — do not redo", ""]
            lines += [f"- {title}" for title in done]
            lines.append("")
        here = tsk.earliest_incomplete(task)
        if here is not None and here < len(plan.phases):
            phase = plan.phases[here]
            lines += ["## Where the work is", "",
                      f"- **{phase.title}**",
                      f"  - verified when: {phase.verified_when}", ""]
        else:
            lines += ["## Where the work is", "",
                      "Every phase has its own PASS.", ""]
    else:
        lines += ["## Plan", "", "No plan was written for this task.", ""]

    verdict = task.verdict or {}
    if verdict.get("state"):
        lines += ["## What the verifier last said", "",
                  f"**{verdict['state']}** — {verdict.get('why', '')}", ""]

    from ai4science.harness.agents.sarsi import questions as qst
    open_questions = [q for q in qst.open_of(config, agent)
                      if q.task_id == task.id]
    if open_questions:
        lines += ["## Waiting on the owner", ""]
        for q in open_questions:
            lines.append(f"- {q.text}" + (f" ({q.why})" if q.why else ""))
        lines.append("")

    if task.grants:
        # named, never read: this file is not a second copy of a credential
        lines += ["## Granted to this task", ""]
        lines += [f"- {g}" for g in task.grants]
        lines.append("")

    root = tsk.evidence_root(agent, task)
    lines += ["## Where the work happens", "", f"`{root}`", ""]
    if task.max_steps or task.max_minutes:
        limits = ([f"{task.max_steps} steps"] if task.max_steps else []) + \
                 ([f"{task.max_minutes} minutes"] if task.max_minutes else [])
        lines += [f"**Budget:** {', '.join(limits)}", ""]

    lines += ["---", "",
              "Written from this task's record when its session ended. It says "
              "what was *established*, not what the last session intended — "
              "anything not here was not recorded."]
    return "\n".join(lines)


def write(config: Config, agent: Agent, task: tsk.Task) -> Path:
    """Write `HANDOFF.md` into the task folder, replacing any earlier one.

    Replaced rather than appended: two handoffs in one file is two accounts of
    where the work is, and the reader cannot tell which is current.
    """
    folder = tsk.dir_of(agent, task.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILE_NAME
    path.write_text(render(config, agent, task))
    return path


def exists(agent: Agent, task: tsk.Task) -> bool:
    return (tsk.dir_of(agent, task.id) / FILE_NAME).exists()
