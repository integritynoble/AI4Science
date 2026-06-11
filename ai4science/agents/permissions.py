"""Permission callbacks for tool-using agents.

The Claude Agent SDK fires ``can_use_tool`` on every tool invocation. We
implement Claude-Code-style permission prompts:

  - Show the agent's proposed action (diff for Edit, content snippet for
    Write, command line for Bash).
  - Ask the user y/N.
  - Reject anything that would touch a path outside the workspace.

Read-only tools (Read, Grep, Glob) are auto-approved.

The "user always reviews" hard rule is preserved at the *change* level:
the agent never edits without an explicit yes for THAT specific change.
"""
from __future__ import annotations

import asyncio
import difflib
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Set

# Lazy import — the SDK is an optional dep.
try:
    from claude_agent_sdk import (  # type: ignore
        PermissionResultAllow, PermissionResultDeny,
    )
    _HAVE_SDK = True
except Exception:
    _HAVE_SDK = False


# Tools that don't modify state — auto-approve, no confirmation.
AUTO_ALLOW_TOOLS: Set[str] = {"Read", "Grep", "Glob", "ListDir", "NotebookRead"}

# Tools that modify state — must confirm.
CONFIRM_TOOLS: Set[str] = {"Edit", "Write", "NotebookEdit", "Bash", "MultiEdit"}


def make_workspace_permission_callback(
    workspace: Path,
    auto_yes: bool = False,
) -> Callable[[str, Dict[str, Any], Any], Awaitable[Any]]:
    """Build an async can_use_tool callback bound to a workspace root.

    Parameters
    ----------
    workspace : Path
        Root that constrains all file paths. Any tool call referencing a
        path outside this root is denied.
    auto_yes : bool
        Skip confirmation prompts (intended for tests and `--yes` mode).
    """
    if not _HAVE_SDK:
        raise RuntimeError("claude-agent-sdk not installed; cannot build permission callback")

    workspace = workspace.resolve()

    async def can_use_tool(tool_name: str, input_dict: Dict[str, Any], _ctx: Any):
        # Read-only tools: always allow.
        if tool_name in AUTO_ALLOW_TOOLS:
            return PermissionResultAllow()

        # Read-only shell commands: allow without prompting (Claude Code parity).
        if tool_name == "Bash":
            from ai4science.harness.permissions import is_read_only_bash
            if is_read_only_bash(input_dict.get("command", "")):
                return PermissionResultAllow()

        # Mutating tools: require confirmation + sandbox check.
        if tool_name in CONFIRM_TOOLS:
            # Sandbox: any file_path arg must resolve inside workspace.
            file_path = input_dict.get("file_path")
            if file_path:
                if not _is_inside_workspace(Path(file_path), workspace):
                    return PermissionResultDeny(
                        message=(f"path {file_path!r} is outside the workspace "
                                 f"({workspace}); ai4science only allows edits "
                                 f"inside the current contribution workspace"),
                        interrupt=False,
                    )

            # Bash: no file_path, but still gated.
            preview = _render_tool_preview(tool_name, input_dict, workspace)
            sys.stderr.write("\n" + preview + "\n")
            sys.stderr.flush()

            if auto_yes:
                sys.stderr.write("[auto-yes] approved\n")
                sys.stderr.flush()
                return PermissionResultAllow()

            approved = await _ask_yes_no(f"Allow {tool_name}? [y/N] ")
            if not approved:
                return PermissionResultDeny(message="user denied", interrupt=False)
            return PermissionResultAllow()

        # Unknown tool — be safe; deny.
        return PermissionResultDeny(
            message=f"unknown tool {tool_name!r}; refusing for safety",
            interrupt=False,
        )

    return can_use_tool


def _is_inside_workspace(p: Path, workspace: Path) -> bool:
    """True iff *p* resolves to a path inside *workspace*."""
    try:
        target = (workspace / p).resolve() if not p.is_absolute() else p.resolve()
        target.relative_to(workspace)
        return True
    except Exception:
        return False


def _render_tool_preview(tool_name: str, input_dict: Dict[str, Any], workspace: Path) -> str:
    """Human-readable preview of a proposed tool call."""
    if tool_name == "Edit":
        file_path = input_dict.get("file_path", "")
        old = input_dict.get("old_string", "")
        new = input_dict.get("new_string", "")
        diff = _unified_diff(file_path, old, new)
        return f"┌── Edit {file_path}\n{diff}\n└──"

    if tool_name == "MultiEdit":
        file_path = input_dict.get("file_path", "")
        edits = input_dict.get("edits", [])
        chunks = [f"┌── MultiEdit {file_path} ({len(edits)} edits)"]
        for i, e in enumerate(edits):
            chunks.append(f"  [{i+1}] " + _unified_diff(
                file_path, e.get("old_string", ""), e.get("new_string", ""),
            ).replace("\n", "\n      "))
        chunks.append("└──")
        return "\n".join(chunks)

    if tool_name == "Write":
        file_path = input_dict.get("file_path", "")
        content = input_dict.get("content", "")
        snippet = content if len(content) <= 1500 else content[:1500] + "\n[... truncated]"
        return f"┌── Write {file_path}\n{snippet}\n└──"

    if tool_name == "Bash":
        cmd = input_dict.get("command", "")
        descr = input_dict.get("description", "")
        return (f"┌── Bash"
                + (f"\n  description: {descr}" if descr else "")
                + f"\n  $ {cmd}\n└──")

    # Fallback: dump input compactly.
    return f"┌── {tool_name}\n  {input_dict}\n└──"


def _unified_diff(file_path: str, old: str, new: str) -> str:
    """Produce a small unified diff for an Edit preview."""
    old_lines = old.splitlines(keepends=True) or [""]
    new_lines = new.splitlines(keepends=True) or [""]
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{file_path}", tofile=f"b/{file_path}",
        n=3,
    ))
    return "".join(diff) if diff else "(empty diff)"


async def _ask_yes_no(prompt: str) -> bool:
    """Async-friendly y/N prompt.

    Falls back to NO when stdin is not a tty (CI, scripted use). Set
    ``AI4SCIENCE_AUTO_YES=1`` to bypass entirely.
    """
    if os.environ.get("AI4SCIENCE_AUTO_YES") == "1":
        return True
    if not sys.stdin.isatty():
        # Non-interactive: be conservative — refuse rather than block.
        sys.stderr.write(f"{prompt}[no tty → denied] ")
        sys.stderr.flush()
        return False
    # Run blocking input() off the event loop.
    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(None, lambda: input(prompt))
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\n[denied]\n")
        return False
    return answer.strip().lower() in ("y", "yes")
