"""`S` — steer the plan's earliest incomplete phase.

The composer writes **one** instruction and types it. What it is *given* matters
more than what it says, so most of this module is the workspace it reads:

| Item | Why it is there |
|---|---|
| the plan, and the phase being driven | the session is told **where it is**, by name |
| the last verdict's reason | so the next prompt addresses what was refused |
| **what the owner said**, either surface | a real console bug: an instruction reached `clarify` and nothing else, so *"use the staging host"* never got in front of the node writing the next prompt |
| its own last few prompts | *do not repeat what already failed* |
| `EC`'s findings | every round the error persists, so it steers around it rather than past it |

Two refusals:

  * **a stale plan is withheld.** Marching a session through phases the owner
    has abandoned is worse than improvising against the goal, so the criteria
    are dropped and the prompt says why.
  * **the composer may not declare the work done.** A model answering `DONE`
    has not verified anything; only the verifier rules, and it runs *before*
    this node, never after.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

from ai4science.harness.agents.sarsi import (ownerlog, resultcheck as rc,
                                             task as tsk)
from ai4science.harness.agents.sarsi.registry import Agent, Config

KEEP_PROMPTS = 5
PROMPTS_NAME = "typed.json"

_CONTRACT = (
    "You are steering another agent's coding session. Write EXACTLY ONE "
    "instruction for its next step — imperative, concrete, and grounded in what "
    "is on screen.\n"
    "You may not declare the work finished: an independent verifier decides "
    "that, and it has already run this round. If you believe there is nothing "
    "left to do, answer with the single word NOTHING.\n"
    "Do not restate the plan. Do not explain yourself. One instruction."
)


@dataclass(frozen=True)
class Composed:
    instruction: Optional[str]
    phase: Optional[str] = None
    note: str = ""


def compose(config: Config, agent: Agent, task: tsk.Task, *, screen: str,
            model: Callable[[str], str]) -> Composed:
    plan = tsk.read_plan(config, agent, task)
    stale = bool(task.plan_stale) or not task.criteria
    phase = None
    if plan is not None and not stale and plan.phases:
        phase = plan.phases[0].title

    prompt = build_prompt(config, agent, task, screen=screen, plan=plan,
                          stale=stale, phase=phase)
    try:
        answer = (model(prompt) or "").strip()
    except Exception as e:
        return Composed(instruction=None, phase=phase,
                        note=f"could not compose: {e}")

    if not answer:
        return Composed(instruction=None, phase=phase, note="nothing to say")
    if answer.upper().startswith(("NOTHING", "DONE")):
        # The composer never rules. If it thinks the work is finished, the
        # verifier is the only thing that may say so — and it runs before this.
        return Composed(instruction=None, phase=phase,
                        note="the composer believes this is finished; only the "
                             "verifier may say so")
    return Composed(instruction=answer, phase=phase)


def build_prompt(config: Config, agent: Agent, task: tsk.Task, *, screen: str,
                 plan, stale: bool, phase: Optional[str]) -> str:
    lines = [_CONTRACT, "", f"GOAL: {task.goal}"]

    if stale:
        # withheld, not deleted — and say why, so the model does not invent
        # phases to fill the gap
        lines.append("PLAN: withheld — it is stale (the owner took the wheel or "
                     "the mission changed). Improvise against the goal alone.")
    elif phase:
        lines.append(f"PHASE YOU ARE DRIVING: {phase}")
        lines.append("CRITERIA — what the verifier must see:")
        lines += [f"  - {c}" for c in task.criteria]

    if task.verdict and task.verdict.get("state") == "FAIL":
        lines.append(f"THE VERIFIER LAST REFUSED THIS: {task.verdict.get('why', '')}")

    said = ownerlog.said(config, agent, limit=5)
    if said:
        lines.append("THE OWNER SAID (authoritative for what they want):")
        lines += [f"  - {e.get('text', '')}" for e in said]

    typed = recent(config, agent, task)
    if typed:
        lines.append("YOU ALREADY TYPED THESE — do not repeat what failed:")
        lines += [f"  - {t}" for t in typed]

    findings = rc.render(rc.scan(screen))
    if findings:
        lines += ["", findings]

    lines += ["", "WHAT IS ON SCREEN NOW:", (screen or "")[-4000:]]
    return "\n".join(lines)


def steer(config: Config, agent: Agent, task: tsk.Task, *, screen: str,
          model: Callable[[str], str], pane: Any) -> Composed:
    """Compose one instruction and type it. Remembers what it typed."""
    out = compose(config, agent, task, screen=screen, model=model)
    if not out.instruction:
        return out
    pane.send((task.session or {}).get("name", ""), out.instruction)
    remember(config, agent, task, out.instruction)
    return out


# ── what it already tried ─────────────────────────────────────────────

def remember(config: Config, agent: Agent, task: tsk.Task, instruction: str) -> None:
    kept = recent(config, agent, task)
    kept.append(instruction)
    _path(agent, task).write_text(json.dumps(kept[-KEEP_PROMPTS:]))


def recent(config: Config, agent: Agent, task: tsk.Task) -> List[str]:
    path = _path(agent, task)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return list(data) if isinstance(data, list) else []
    except Exception:
        return []


def _path(agent: Agent, task: tsk.Task) -> Path:
    path = tsk.dir_of(agent, task.id) / PROMPTS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def claude_model(*, timeout: float = 180.0) -> Callable[[str], str]:
    """The composer's own engine — the local Claude CLI, headless."""
    import subprocess

    def call(prompt: str) -> str:
        proc = subprocess.run(["claude", "-p"], input=prompt, capture_output=True,
                              text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "").strip()[:200])
        return proc.stdout

    return call
