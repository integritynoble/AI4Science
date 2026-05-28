"""Shared helpers for building agent prompts and inlining workspace context.

Both ClaudeAgent and CodexAgent use these to keep their prompts and
read-only context-passing semantics identical. The agents differ only in
the underlying transport (SDK call vs subprocess call).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

# Bounded prompt budget — keeps single-call costs predictable.
PER_FILE_CHAR_BUDGET = 8_000
MAX_FILES_INLINED = 8


def build_context_blob(workspace: Path, context_files: List[Path]) -> str:
    """Inline up to MAX_FILES_INLINED files (truncated to PER_FILE_CHAR_BUDGET each)."""
    blobs: List[str] = []
    for cf in context_files[:MAX_FILES_INLINED]:
        try:
            text = cf.read_text(encoding="utf-8")
        except Exception as e:
            blobs.append(f"\n### {cf.name} (unreadable: {e})\n")
            continue
        truncated = len(text) > PER_FILE_CHAR_BUDGET
        if truncated:
            text = text[:PER_FILE_CHAR_BUDGET] + "\n[...truncated...]"
        try:
            rel = cf.relative_to(workspace) if cf.is_relative_to(workspace) else cf
        except Exception:
            rel = cf
        blobs.append(f"\n### `{rel}`\n```\n{text}\n```\n")
    if len(context_files) > MAX_FILES_INLINED:
        blobs.append(f"\n[{len(context_files) - MAX_FILES_INLINED} more files omitted]\n")
    return "".join(blobs) if blobs else "_(no context files attached)_\n"


def compose_prompt(user_prompt: str, workspace: Path,
                   context_files: List[Path], embed_system: str = "",
                   tools_enabled: bool = False) -> str:
    """Compose a single prompt string.

    Parameters
    ----------
    user_prompt : str
        The raw user request.
    workspace : Path
        Workspace root (its name appears in the prompt for grounding).
    context_files : List[Path]
        Files to inline into the prompt body.
    embed_system : str
        Non-empty for agents (like Codex) whose CLI doesn't accept a
        separate system_prompt option — we prepend the AI4Science system
        prompt into the same prompt blob.
    tools_enabled : bool
        If True, the closing "Output format" section instructs the agent
        to USE its tools (Edit/Write/Bash) for changes. If False, it
        explicitly forbids file writes (the read-only contract).
    """
    ctx_blob = build_context_blob(workspace, context_files)
    parts: List[str] = []
    if embed_system:
        parts.append(f"## AI4Science system context\n\n{embed_system}\n")
    parts.append(f"## User request\n\n{user_prompt}\n")
    parts.append(f"## Workspace context\n\nworkspace: `{workspace}`\n{ctx_blob}")
    if tools_enabled:
        parts.append(
            "## Output format\n\n"
            "You have Edit/Write/Bash tools available, scoped to the workspace "
            "above. When the user asks for a concrete change, USE the appropriate "
            "tool to make the change directly — don't just describe what should "
            "change. Read the file first, then Edit. Run `ai4science validate` "
            "via Bash when finished to confirm the change parses. Each tool call "
            "will prompt the user for confirmation before it takes effect."
        )
    else:
        parts.append(
            "## Output format\n\n"
            "Respond with helpful suggestions and draft text only. "
            "DO NOT attempt to write files; the user will copy what they want "
            "into their editor."
        )
    return "\n".join(parts)
