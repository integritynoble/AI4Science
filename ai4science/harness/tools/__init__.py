from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from ai4science.harness.tools.base import Registry, Tool
from ai4science.harness.tools import fs, shell

_STR = {"type": "string"}


def _outside(writable_roots: Optional[Sequence]) -> str:
    """What to add to a SANDBOXED tool's description, given extra roots.

    Making the plan's working directory writable was half the job. The live run
    after it showed the other half: the agent still reached for a heredoc,
    because nothing told it the tool would work there and a shell redirect
    always had. Capability the model cannot discover changes nothing, so the
    directories are NAMED — "paths outside the workspace are refused" would
    leave it guessing which ones.
    """
    roots = [str(Path(r)) for r in (writable_roots or []) if str(r)]
    if not roots:
        # Nothing declared: say nothing. A sentence about a boundary that has
        # not moved is noise the model must reconcile against what it observes.
        return ""
    return (" Besides the workspace, this session may also write inside: "
            + ", ".join(roots) + ".")


def default_registry(writable_roots: Optional[List[Path]] = None) -> Registry:
    outside = _outside(writable_roots)
    reg = Registry()
    reg.add(Tool("read", "Read a file (returns numbered lines).",
                 {"type": "object", "properties": {"path": _STR}, "required": ["path"]},
                 fs.read, mutating=False))
    reg.add(Tool("write", "Write (overwrite) a file." + outside,
                 {"type": "object", "properties": {"path": _STR, "content": _STR},
                  "required": ["path", "content"]}, fs.write, mutating=True))
    reg.add(Tool("edit", "Replace a unique old string with new in a file." + outside,
                 {"type": "object", "properties": {"path": _STR, "old": _STR, "new": _STR},
                  "required": ["path", "old", "new"]}, fs.edit, mutating=True))
    reg.add(Tool("bash", "Run a shell command in the workspace."
                 + (" To write or change a NAMED file, use `write`/`edit` "
                    "instead: a shell redirect names no file, so nothing "
                    "afterwards can report what it touched." if outside else ""),
                 {"type": "object", "properties": {"cmd": _STR}, "required": ["cmd"]},
                 shell.bash, mutating=True, streams=True))
    reg.add(Tool(
        "grep",
        "Fast regex content search (ripgrep-backed, prunes .git/node_modules/"
        ".venv/etc). PREFER THIS over `grep`/`find` in bash. Searches the "
        "project workspace by default; pass `path` to narrow to a SUBDIRECTORY. "
        "`glob` filters files (e.g. '*.py'). Returns 'path:line:text' rows.",
        {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "regex matched against file contents"},
            "path": {"type": "string", "description": "optional subdirectory to narrow the search. Default: the project workspace."},
            "glob": {"type": "string", "description": "optional filename filter, e.g. '*.md'"}},
         "required": ["pattern"]},
        fs.grep, mutating=False))
    reg.add(Tool(
        "glob",
        "Fast file/folder NAME search by glob pattern (e.g. '*lowdose*', "
        "'**/*.py'). Returns matching files AND folders, newest first. PREFER "
        "THIS over `find` in bash. Searches the project workspace by default; "
        "pass `path` to narrow to a SUBDIRECTORY.",
        {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "glob matched against file/folder names and paths, e.g. '**/*.py'"},
            "path": {"type": "string", "description": "optional subdirectory to narrow the search. Default: the project workspace."}},
         "required": ["pattern"]},
        fs.glob, mutating=False))
    return reg


__all__ = ["Registry", "Tool", "default_registry", "fs", "shell"]
