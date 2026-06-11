from __future__ import annotations

from pathlib import Path
from typing import Callable, List

from ai4science.harness.events import Message, TextDelta, ToolCall, Usage, Done
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools.base import Registry

MAX_TOOL_ITERATIONS = 50


def run_loop(*, adapter, model: str, reasoning: str, history: List[Message],
             workspace: Path, registry: Registry, gate: PermissionGate,
             on_text: Callable[[str], None], meter: Callable[[Usage], None],
             on_tool: Callable[[str], None] = lambda name: None,
             on_tool_start: Callable[[str, dict], None] = lambda name, args: None,
             on_tool_end: Callable[[str, str], None] = lambda name, result: None) -> str:
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
            on_tool_start(tc.name, tc.arguments)
            ok, reason = gate.allow(tc.name, tc.arguments)
            streamed = False
            if not ok:
                result = f"[blocked] {reason}"
            else:
                try:
                    tool = registry.get(tc.name)
                    if tool.streams:
                        result = tool.func(workspace, **tc.arguments, _sink=on_text)
                        streamed = True
                    else:
                        result = tool.func(workspace, **tc.arguments)
                    on_tool(tc.name)   # contribution-usage hook (agent-mining)
                except Exception as exc:
                    result = f"[error] {exc}"
            # Streaming tools already printed their output live — suppress the
            # `⎿` summary (empty string formats to nothing) to avoid doubling.
            on_tool_end(tc.name, "" if streamed else str(result))
            history.append(Message(role="tool", content=str(result), tool_call_id=tc.id))
    else:
        note = (f"\n[harness] stopped after {MAX_TOOL_ITERATIONS} tool iterations "
                f"(possible truncation)")
        on_text(note)
        final_text_parts.append(note)

    return "".join(final_text_parts)
