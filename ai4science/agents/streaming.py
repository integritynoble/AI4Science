"""Pure helpers for streaming output + inline tool visibility.

Kept free of SDK transport so they're unit-testable. The chat REPL wires
these into a rich.Live render loop.

  extract_text_delta(event)   — pull incremental text from a StreamEvent.event
  format_tool_use(name, inp)  — a "⏺ Tool(args)" line for a tool call
  format_tool_result(content, is_error) — a "⎿ ..." result summary line
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def extract_text_delta(event: Any) -> Optional[str]:
    """Return the incremental text from a raw streaming event, or None.

    The SDK's StreamEvent.event carries the raw Anthropic SSE event dict,
    e.g. {"type": "content_block_delta", "delta": {"type": "text_delta",
    "text": "..."}}.
    """
    if not isinstance(event, dict):
        return None
    if event.get("type") == "content_block_delta":
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            return delta.get("text")
        # thinking deltas are surfaced separately; ignore here
    return None


def format_tool_use(name: str, tool_input: Dict[str, Any]) -> str:
    """One-line summary of a tool call, à la Claude Code's ⏺ lines."""
    arg = _summarize_tool_args(name, tool_input or {})
    return f"⏺ [bold cyan]{name}[/bold cyan]({arg})"


def _summarize_tool_args(name: str, inp: Dict[str, Any]) -> str:
    """Pick the most informative single arg for the tool."""
    # File-path tools
    for key in ("file_path", "path", "notebook_path"):
        if key in inp:
            val = str(inp[key])
            return _short(val)
    # Bash
    if name == "Bash" and "command" in inp:
        return _short(str(inp["command"]), 60)
    # Grep / Glob
    if "pattern" in inp:
        return _short(str(inp["pattern"]))
    # Task (sub-agent delegation)
    if name == "Task":
        sub = inp.get("subagent_type") or inp.get("description") or ""
        return _short(str(sub))
    # MCP tools — show the workspace/benchmark hint if present
    if "benchmark" in inp:
        return _short(str(inp["benchmark"]))
    if "artifact" in inp:
        return _short(str(inp["artifact"]))
    # Fallback: first key=value
    if inp:
        k = next(iter(inp))
        return f"{k}={_short(str(inp[k]))}"
    return ""


def format_tool_result(content: Any, is_error: bool = False) -> str:
    """Compact one-line summary of a tool result."""
    text = _result_to_text(content)
    text = text.replace("\n", " ").strip()
    marker = "[red]⎿ error:[/red]" if is_error else "[dim]⎿[/dim]"
    return f"  {marker} [dim]{_short(text, 80)}[/dim]"


def _result_to_text(content: Any) -> str:
    """Tool results may be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(getattr(item, "text", item)))
        return " ".join(p for p in parts if p)
    return str(content)


def _short(s: str, n: int = 50) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"
