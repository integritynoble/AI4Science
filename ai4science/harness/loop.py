from __future__ import annotations

from pathlib import Path
from typing import Callable, List

from ai4science.harness.events import Message, TextDelta, ToolCall, Usage, Done
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools.base import Registry

MAX_TOOL_ITERATIONS = 50


def run_loop(*, adapter, model: str, reasoning: str, history: List[Message],
             workspace: Path, registry: Registry, gate: PermissionGate,
             on_text: Callable[[str], None], meter: Callable[[Usage], None]) -> str:
    """Drive one user turn to completion (text + any tool calls). Returns final text."""
    final_text_parts: List[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        text_buf: List[str] = []
        calls: List[ToolCall] = []
        for ev in adapter.stream(history, registry.specs(), model=model, reasoning=reasoning):
            if isinstance(ev, TextDelta):
                text_buf.append(ev.text)
                on_text(ev.text)
            elif isinstance(ev, ToolCall):
                calls.append(ev)
            elif isinstance(ev, Usage):
                meter(ev)
            elif isinstance(ev, Done):
                pass

        assistant_text = "".join(text_buf)
        history.append(Message(role="assistant", content=assistant_text, tool_calls=list(calls)))
        if assistant_text:
            final_text_parts.append(assistant_text)

        if not calls:
            break

        for tc in calls:
            ok, reason = gate.allow(tc.name, tc.arguments)
            if not ok:
                result = f"[blocked] {reason}"
            else:
                try:
                    tool = registry.get(tc.name)
                    if tool.streams:
                        result = tool.func(workspace, **tc.arguments, _sink=on_text)
                    else:
                        result = tool.func(workspace, **tc.arguments)
                except Exception as exc:
                    result = f"[error] {exc}"
            history.append(Message(role="tool", content=str(result), tool_call_id=tc.id))

    return "".join(final_text_parts)
