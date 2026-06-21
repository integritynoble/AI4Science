from __future__ import annotations

from pathlib import Path
from typing import Callable, List

from ai4science.harness import interrupt
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
        stream_interrupted = False
        for ev in adapter.stream(history, registry.specs(), model=model, reasoning=reasoning):
            # Honor Ctrl-C / Esc mid-stream: stop consuming tokens at once (the
            # generator closes → the LLM request aborts) instead of waiting for
            # the whole response to finish. This is what makes Ctrl-C feel instant.
            if interrupt.requested():
                stream_interrupted = True
                break
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

        if stream_interrupted:
            # End the turn cleanly. Record only the partial TEXT (drop any
            # half-formed tool_calls so the next request has no dangling tool_use).
            if assistant_text:
                history.append(Message(role="assistant", content=assistant_text))
                final_text_parts.append(assistant_text)
            interrupt.clear()
            on_text("\n\x1b[2m[interrupted — type a new message]\x1b[0m\n")
            break

        history.append(Message(role="assistant", content=assistant_text, tool_calls=list(calls)))
        if assistant_text:
            final_text_parts.append(assistant_text)

        if not calls:
            break

        interrupted = False
        for tc in calls:
            if interrupted:
                # Every tool_call id still needs an answer for the next API
                # call — record the skip without executing.
                history.append(Message(role="tool",
                                       content="[skipped — user interrupted the turn]",
                                       tool_call_id=tc.id))
                continue
            on_tool_start(tc.name, tc.arguments)
            ok, reason = gate.allow(tc.name, tc.arguments)
            streamed = False
            _supp = {"n": 0}
            if not ok:
                result = f"[blocked] {reason}"
            else:
                try:
                    tool = registry.get(tc.name)
                    if tool.streams:
                        # Cap the LIVE display like Claude Code: stream just a
                        # short peek, then hide the rest (the agent still receives
                        # the FULL output via the return value). Default 6; set
                        # AI4SCIENCE_TOOL_DISPLAY_LINES=0 to fully collapse (show
                        # only the '⎿ (+N lines)' note) or higher to see more.
                        import os as _os
                        try:
                            _cap = max(0, int(_os.environ.get(
                                "AI4SCIENCE_TOOL_DISPLAY_LINES", "6")))
                        except (TypeError, ValueError):
                            _cap = 6
                        _seen = {"n": 0}

                        def _capped(s, _on=on_text, _seen=_seen, _supp=_supp, _cap=_cap):
                            if _seen["n"] < _cap:
                                _on(s)
                                _seen["n"] += 1
                            else:
                                _supp["n"] += 1

                        result = tool.func(workspace, **tc.arguments, _sink=_capped)
                        streamed = True
                    else:
                        result = tool.func(workspace, **tc.arguments)
                    on_tool(tc.name)   # contribution-usage hook (agent-mining)
                except Exception as exc:
                    result = f"[error] {exc}"
            # Streaming tools printed their (capped) output live. If we hid lines,
            # show a dim Claude-Code-style `⎿ (+N more lines)` note; otherwise
            # suppress the `⎿` summary (empty string) to avoid doubling.
            if streamed and _supp["n"] > 0:
                on_text(f"\x1b[2m  ⎿ (+{_supp['n']} more lines)\x1b[0m\n")
            on_tool_end(tc.name, "" if streamed else str(result))
            history.append(Message(role="tool", content=str(result), tool_call_id=tc.id))
            if interrupt.requested():
                interrupted = True
        if interrupted:
            interrupt.clear()                     # consumed — don't leak
            note = "\n[harness] turn interrupted by user (Esc / Ctrl+C)"
            on_text(note)
            final_text_parts.append(note)
            break
    else:
        note = (f"\n[harness] stopped after {MAX_TOOL_ITERATIONS} tool iterations "
                f"(possible truncation)")
        on_text(note)
        final_text_parts.append(note)

    return "".join(final_text_parts)
