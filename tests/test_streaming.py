"""Tests for the streaming + tool-visibility helpers (pure functions)."""
from __future__ import annotations

from ai4science.agents.streaming import (
    extract_text_delta, format_tool_use, format_tool_result,
)


# ─── extract_text_delta ──────────────────────────────────────────────


def test_extract_text_delta_from_content_block_delta():
    event = {"type": "content_block_delta",
             "delta": {"type": "text_delta", "text": "hello"}}
    assert extract_text_delta(event) == "hello"


def test_extract_text_delta_ignores_non_text_delta():
    event = {"type": "content_block_delta",
             "delta": {"type": "thinking_delta", "thinking": "hmm"}}
    assert extract_text_delta(event) is None


def test_extract_text_delta_ignores_other_event_types():
    assert extract_text_delta({"type": "message_start"}) is None
    assert extract_text_delta({"type": "content_block_stop"}) is None


def test_extract_text_delta_handles_non_dict():
    assert extract_text_delta(None) is None
    assert extract_text_delta("not a dict") is None
    assert extract_text_delta(42) is None


# ─── format_tool_use ─────────────────────────────────────────────────


def test_format_tool_use_file_path():
    out = format_tool_use("Edit", {"file_path": "spec.md", "old_string": "a", "new_string": "b"})
    assert "Edit" in out
    assert "spec.md" in out


def test_format_tool_use_bash_shows_command():
    out = format_tool_use("Bash", {"command": "ai4science validate"})
    assert "Bash" in out
    assert "ai4science validate" in out


def test_format_tool_use_grep_shows_pattern():
    out = format_tool_use("Grep", {"pattern": "tolerance_epsilon"})
    assert "tolerance_epsilon" in out


def test_format_tool_use_task_shows_subagent():
    out = format_tool_use("Task", {"subagent_type": "physics-reviewer",
                                   "description": "review spec"})
    assert "physics-reviewer" in out


def test_format_tool_use_mcp_benchmark_arg():
    out = format_tool_use("mcp__pwm__pwm_judge_cassi", {"benchmark": "benchmark_t2.md"})
    assert "benchmark_t2.md" in out


def test_format_tool_use_truncates_long_args():
    long_cmd = "x" * 200
    out = format_tool_use("Bash", {"command": long_cmd})
    # Truncated with an ellipsis; shouldn't contain the full 200-char string.
    assert "…" in out
    assert long_cmd not in out


# ─── format_tool_result ──────────────────────────────────────────────


def test_format_tool_result_string():
    out = format_tool_result("validation ok", is_error=False)
    assert "validation ok" in out
    assert "⎿" in out


def test_format_tool_result_error_marker():
    out = format_tool_result("file not found", is_error=True)
    assert "error" in out.lower()


def test_format_tool_result_list_of_blocks():
    content = [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]
    out = format_tool_result(content)
    assert "first" in out
    assert "second" in out


def test_format_tool_result_collapses_newlines():
    out = format_tool_result("line one\nline two\nline three")
    # Newlines collapsed to spaces so it stays a single ⎿ line.
    assert "\n" not in out.replace("\\n", "")
