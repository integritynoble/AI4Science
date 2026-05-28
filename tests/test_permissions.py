"""Tests for the permission callback (path sandboxing + tool gating).

These test the LOGIC of the callback without actually running the SDK.
They require claude-agent-sdk (skipped otherwise) because the callback
returns PermissionResultAllow / PermissionResultDeny from the SDK.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

# Skip the entire module if the SDK isn't installed (it's an optional dep).
pytest.importorskip("claude_agent_sdk")

from ai4science.agents.permissions import (
    AUTO_ALLOW_TOOLS, CONFIRM_TOOLS,
    _is_inside_workspace, _unified_diff,
    make_workspace_permission_callback,
)


# ─── Path sandbox ─────────────────────────────────────────────────────


def test_path_inside_workspace_is_accepted(tmp_path):
    f = tmp_path / "principle.md"
    f.write_text("hi")
    assert _is_inside_workspace(f, tmp_path) is True


def test_relative_path_resolves_inside_workspace(tmp_path):
    """Relative paths are joined to workspace and accepted if inside."""
    assert _is_inside_workspace(Path("principle.md"), tmp_path) is True


def test_path_outside_workspace_is_rejected(tmp_path):
    other = tmp_path.parent / "elsewhere.md"
    assert _is_inside_workspace(other, tmp_path) is False


def test_path_with_traversal_is_rejected(tmp_path):
    """../escape attempts must be caught."""
    assert _is_inside_workspace(Path("../../etc/passwd"), tmp_path) is False


# ─── Diff preview ────────────────────────────────────────────────────


def test_unified_diff_includes_both_files():
    diff = _unified_diff("foo.md", "hello world\n", "hello there\n")
    assert "foo.md" in diff
    assert "+hello there" in diff
    assert "-hello world" in diff


def test_unified_diff_empty_strings():
    assert _unified_diff("foo.md", "", "") == "(empty diff)"


# ─── Tool classification ─────────────────────────────────────────────


def test_auto_allow_tools_does_not_overlap_confirm_tools():
    assert AUTO_ALLOW_TOOLS.isdisjoint(CONFIRM_TOOLS)


def test_read_grep_glob_are_auto_allowed():
    assert "Read" in AUTO_ALLOW_TOOLS
    assert "Grep" in AUTO_ALLOW_TOOLS
    assert "Glob" in AUTO_ALLOW_TOOLS


def test_edit_write_bash_require_confirmation():
    assert "Edit" in CONFIRM_TOOLS
    assert "Write" in CONFIRM_TOOLS
    assert "Bash" in CONFIRM_TOOLS


# ─── Callback wiring ──────────────────────────────────────────────────


def test_callback_auto_allows_read(tmp_path):
    cb = make_workspace_permission_callback(tmp_path, auto_yes=False)
    result = asyncio.run(cb("Read", {"file_path": str(tmp_path / "spec.md")}, None))
    from claude_agent_sdk import PermissionResultAllow
    assert isinstance(result, PermissionResultAllow)


def test_callback_denies_edit_outside_workspace(tmp_path):
    cb = make_workspace_permission_callback(tmp_path, auto_yes=True)
    outside = tmp_path.parent / "escape.md"
    result = asyncio.run(cb("Edit", {
        "file_path": str(outside),
        "old_string": "x",
        "new_string": "y",
    }, None))
    from claude_agent_sdk import PermissionResultDeny
    assert isinstance(result, PermissionResultDeny)
    assert "outside the workspace" in result.message


def test_callback_allows_edit_inside_workspace_with_auto_yes(tmp_path):
    cb = make_workspace_permission_callback(tmp_path, auto_yes=True)
    inside = tmp_path / "spec.md"
    result = asyncio.run(cb("Edit", {
        "file_path": str(inside),
        "old_string": "old",
        "new_string": "new",
    }, None))
    from claude_agent_sdk import PermissionResultAllow
    assert isinstance(result, PermissionResultAllow)


def test_callback_denies_unknown_tool(tmp_path):
    cb = make_workspace_permission_callback(tmp_path, auto_yes=True)
    result = asyncio.run(cb("DangerousNewTool", {"arg": "value"}, None))
    from claude_agent_sdk import PermissionResultDeny
    assert isinstance(result, PermissionResultDeny)
    assert "unknown tool" in result.message.lower()


def test_callback_allows_bash_with_auto_yes(tmp_path):
    cb = make_workspace_permission_callback(tmp_path, auto_yes=True)
    result = asyncio.run(cb("Bash", {"command": "ls -la"}, None))
    from claude_agent_sdk import PermissionResultAllow
    assert isinstance(result, PermissionResultAllow)
