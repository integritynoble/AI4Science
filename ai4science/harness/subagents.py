from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

from ai4science.harness.tools.base import Tool

SUBAGENTS: Dict[str, Dict] = {
    "general": {
        "description": "A general-purpose worker for a focused sub-task.",
        "system_prompt": "You are a focused sub-agent. Complete the delegated "
                         "task and report a concise result. Do not ask questions.",
    },
    "physics-reviewer": {
        "description": "Reviews a PWM submission for physical consistency.",
        "system_prompt": "You are a physics reviewer. Inspect the workspace and "
                         "report concerns about physical consistency. You cannot "
                         "override the deterministic Physics Judge.",
    },
    "schema-validator": {
        "description": "Checks PWM artifacts against their schemas.",
        "system_prompt": "You validate PWM artifact schemas and report mismatches.",
    },
}

MAX_SUBAGENT_DEPTH = 2


def make_task_tool(*, session_factory: Callable[..., object], depth: int,
                   max_depth: int = MAX_SUBAGENT_DEPTH) -> Tool:
    """Return a `task` Tool that delegates to a nested AgentSession.

    session_factory(subagent_type=str, depth=int) -> AgentSession (auto-approve).
    Depth-guarded to prevent unbounded recursion.
    """
    names = ", ".join(sorted(SUBAGENTS))

    def _task(workspace: Path, *, subagent_type: str, prompt: str) -> str:
        if depth >= max_depth:
            return f"[task] refused: max sub-agent depth ({max_depth}) reached"
        if subagent_type not in SUBAGENTS:
            return f"[task] unknown subagent_type {subagent_type!r}; available: {names}"
        session = session_factory(subagent_type=subagent_type, depth=depth + 1)
        sys_prompt = SUBAGENTS[subagent_type]["system_prompt"]
        return session.run_turn(f"{sys_prompt}\n\nTASK: {prompt}")

    return Tool(
        name="task",
        description=("Delegate a focused sub-task to a fresh sub-agent. "
                     f"subagent_type one of: {names}."),
        parameters={"type": "object",
                    "properties": {"subagent_type": {"type": "string"},
                                   "prompt": {"type": "string"}},
                    "required": ["subagent_type", "prompt"]},
        func=_task, mutating=False,
    )
