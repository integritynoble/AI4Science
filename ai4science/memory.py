"""Project memory — load a per-workspace instruction file into the system prompt.

Mirrors Claude Code's CLAUDE.md behavior. We look for, in priority order:

    CLAUDE.md, AI4SCIENCE.md, AGENTS.md

in the workspace root. The first one found is appended to the agent's
system prompt so per-project conventions persist across sessions without
the user re-stating them every time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

MEMORY_FILENAMES = ("CLAUDE.md", "AI4SCIENCE.md", "AGENTS.md")

# Bound the injected size so a huge memory file can't blow the prompt.
MAX_MEMORY_CHARS = 16_000


def find_memory_file(workspace: Path) -> Optional[Path]:
    """Return the first memory file present in the workspace, or None."""
    workspace = workspace.resolve()
    for name in MEMORY_FILENAMES:
        p = workspace / name
        if p.is_file():
            return p
    return None


def load_project_memory(workspace: Path) -> Tuple[Optional[str], Optional[Path]]:
    """Return (memory_text, path) or (None, None) if no memory file exists."""
    path = find_memory_file(workspace)
    if path is None:
        return None, None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, None
    if len(text) > MAX_MEMORY_CHARS:
        text = text[:MAX_MEMORY_CHARS] + "\n[... project memory truncated]"
    return text, path


def augment_system_prompt(base_prompt: str, workspace: Path) -> str:
    """Append project memory (if any) to a base system prompt."""
    text, path = load_project_memory(workspace)
    if not text:
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        f"## Project memory ({path.name})\n\n"
        f"The workspace ships a project-instruction file. Treat the following "
        f"as authoritative project conventions, secondary only to the user's "
        f"direct requests:\n\n{text}\n"
    )
