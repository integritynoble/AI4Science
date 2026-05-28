"""Custom (user-defined) slash commands — like Claude Code's .claude/commands/.

A file ``<name>.md`` becomes the slash command ``/<name>``. Its contents
are a prompt template that's expanded and sent to the agent as a normal
turn. ``$ARGUMENTS`` (and ``$1``, ``$2`` … positional) are substituted
from whatever the user types after the command.

Lookup order (first wins, project overrides user):
  <workspace>/.ai4science/commands/*.md
  ~/.config/ai4science/commands/*.md
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Dict, List


def command_dirs(workspace: Path) -> List[Path]:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [
        Path(workspace).resolve() / ".ai4science" / "commands",
        base / "ai4science" / "commands",
    ]


def load_custom_commands(workspace: Path) -> Dict[str, Path]:
    """Map command name → file path. Project dir overrides the user dir."""
    cmds: Dict[str, Path] = {}
    for d in command_dirs(workspace):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            name = f.stem.lower()
            cmds.setdefault(name, f)   # first dir (project) wins
    return cmds


def expand_command(path: Path, args: str) -> str:
    """Load a command template and substitute arguments.

    - ``$ARGUMENTS`` → the full argument string
    - ``$1``, ``$2`` … → positional args (shlex-split); missing → empty
    """
    text = path.read_text(encoding="utf-8")
    text = text.replace("$ARGUMENTS", args)
    try:
        positional = shlex.split(args)
    except ValueError:
        positional = args.split()
    for i, val in enumerate(positional, start=1):
        text = text.replace(f"${i}", val)
    # Any remaining unfilled positionals → empty string.
    import re
    text = re.sub(r"\$\d+", "", text)
    return text
