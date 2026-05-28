"""Tests for the non-TTY plain streaming renderer.

These feed a fake async message stream (built from the real SDK dataclasses)
into _render_plain and capture output via a StringIO-backed Console — no
network, no real client.
"""
from __future__ import annotations

import asyncio
import io

import pytest
from rich.console import Console

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import (   # type: ignore
    AssistantMessage, UserMessage, ResultMessage, StreamEvent,
    TextBlock, ToolUseBlock, ToolResultBlock,
)
from ai4science.commands.chat import _render_plain


def _delta_event(text):
    return StreamEvent(
        uuid="u", session_id="s", parent_tool_use_id=None,
        event={"type": "content_block_delta",
               "delta": {"type": "text_delta", "text": text}},
    )


async def _astream(items):
    for it in items:
        yield it


def _run(messages) -> str:
    buf = io.StringIO()
    out = Console(file=buf, force_terminal=False, width=100)
    asyncio.run(_render_plain(_astream(messages), out))
    return buf.getvalue()


def _result():
    # ResultMessage has required fields across SDK versions; build leniently.
    try:
        return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1,
                             is_error=False, num_turns=1, session_id="s",
                             total_cost_usd=0.0, usage={}, result="ok")
    except TypeError:
        # Fall back: minimal construction if the signature differs.
        import dataclasses
        fields = {f.name: None for f in dataclasses.fields(ResultMessage)}
        return ResultMessage(**fields)


# ─── text streaming ──────────────────────────────────────────────────


def test_streams_text_deltas():
    out = _run([_delta_event("Hello "), _delta_event("world."), _result()])
    assert "Hello world." in out


def test_tool_use_line_rendered():
    msgs = [
        _delta_event("Reading the spec.\n"),
        AssistantMessage(content=[ToolUseBlock(id="t1", name="Read",
                                               input={"file_path": "spec.md"})],
                         model="claude"),
        _result(),
    ]
    out = _run(msgs)
    assert "Read" in out
    assert "spec.md" in out


def test_tool_result_line_rendered():
    msgs = [
        AssistantMessage(content=[ToolUseBlock(id="t1", name="Bash",
                                               input={"command": "ls"})],
                         model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="t1",
                                             content="file1 file2", is_error=False)]),
        _result(),
    ]
    out = _run(msgs)
    assert "Bash" in out
    assert "file1" in out


def test_textblock_fallback_when_no_deltas():
    """If no StreamEvent deltas arrive, the complete TextBlock is printed."""
    msgs = [
        AssistantMessage(content=[TextBlock(text="Full block answer.")],
                         model="claude"),
        _result(),
    ]
    out = _run(msgs)
    assert "Full block answer." in out


def test_textblock_not_duplicated_when_streamed():
    """When deltas already streamed the text, the AssistantMessage TextBlock
    must NOT be printed again."""
    msgs = [
        _delta_event("Streamed answer."),
        AssistantMessage(content=[TextBlock(text="Streamed answer.")],
                         model="claude"),
        _result(),
    ]
    out = _run(msgs)
    # Exactly one occurrence.
    assert out.count("Streamed answer.") == 1


def test_stops_at_result_message():
    """Messages after ResultMessage are not rendered (turn boundary)."""
    msgs = [
        _delta_event("before."),
        _result(),
        _delta_event("AFTER-should-not-appear"),
    ]
    out = _run(msgs)
    assert "before." in out
    assert "AFTER-should-not-appear" not in out
