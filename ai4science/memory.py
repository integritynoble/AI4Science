"""Project memory — load a per-workspace instruction file into the system prompt.

Mirrors Claude Code's CLAUDE.md behavior, but AI4Science-branded. We look
for, in priority order:

    AI4SCIENCE.md, CLAUDE.md, AGENTS.md

in the workspace root. AI4SCIENCE.md is preferred (this is the AI4Science
tool); CLAUDE.md and AGENTS.md are accepted as fallbacks for cross-tool
compatibility. The first one found is appended to the agent's system
prompt so per-project conventions persist across sessions without the
user re-stating them every time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

MEMORY_FILENAMES = ("AI4SCIENCE.md", "CLAUDE.md", "AGENTS.md")

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
    """Append the workspace location + project memory (if any) to a base prompt.

    The workspace block is ALWAYS added: it tells the agent its working
    directory up front so it targets the right path on the first file
    operation instead of guessing a home dir (e.g. ``/Users/<name>``) and
    burning a turn recovering from an out-of-workspace write.
    """
    workspace = workspace.resolve()
    prompt = (
        f"{base_prompt}\n\n"
        f"## Workspace\n\n"
        f"Your working directory is `{workspace}`. All file operations run from "
        f"here — create and read files using paths relative to it (e.g. "
        f"`spec.md`, `code/run_solver.py`) or absolute paths under it. Do not "
        f"guess a home directory, and do not write outside this directory: the "
        f"sandbox will deny it.\n"
    )
    text, path = load_project_memory(workspace)
    if text:
        prompt += (
            f"\n## Project memory ({path.name})\n\n"
            f"The workspace ships a project-instruction file. Treat the following "
            f"as authoritative project conventions, secondary only to the user's "
            f"direct requests:\n\n{text}\n"
        )
    return prompt
