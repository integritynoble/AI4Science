from __future__ import annotations

from ai4science.harness.tools.base import Registry, Tool
from ai4science.harness.tools import fs, shell

_STR = {"type": "string"}


def default_registry() -> Registry:
    reg = Registry()
    reg.add(Tool("read", "Read a file (returns numbered lines).",
                 {"type": "object", "properties": {"path": _STR}, "required": ["path"]},
                 fs.read, mutating=False))
    reg.add(Tool("write", "Write (overwrite) a file.",
                 {"type": "object", "properties": {"path": _STR, "content": _STR},
                  "required": ["path", "content"]}, fs.write, mutating=True))
    reg.add(Tool("edit", "Replace a unique old string with new in a file.",
                 {"type": "object", "properties": {"path": _STR, "old": _STR, "new": _STR},
                  "required": ["path", "old", "new"]}, fs.edit, mutating=True))
    reg.add(Tool("bash", "Run a shell command in the workspace.",
                 {"type": "object", "properties": {"cmd": _STR}, "required": ["cmd"]},
                 shell.bash, mutating=True, streams=True))
    reg.add(Tool(
        "grep",
        "Fast regex content search (ripgrep-backed, prunes .git/node_modules/"
        ".venv/etc). PREFER THIS over `grep`/`find` in bash. `path` sets the "
        "root and may be ABSOLUTE to search anywhere on the machine (e.g. "
        "'/home/user' or '/'); default is the workspace. `glob` filters files "
        "(e.g. '*.py'). Returns 'path:line:text' rows.",
        {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "regex matched against file contents"},
            "path": {"type": "string", "description": "search root; absolute path searches outside the workspace. Default: workspace."},
            "glob": {"type": "string", "description": "optional filename filter, e.g. '*.md'"}},
         "required": ["pattern"]},
        fs.grep, mutating=False))
    reg.add(Tool(
        "glob",
        "Fast file/folder NAME search by glob pattern (e.g. '*lowdose*', "
        "'**/*.py'). Returns matching files AND folders. PREFER THIS over "
        "`find` in bash. `path` sets the root and may be ABSOLUTE to search "
        "anywhere on the machine; default is the workspace.",
        {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "glob matched against file/folder names and paths"},
            "path": {"type": "string", "description": "search root; absolute path searches outside the workspace. Default: workspace."}},
         "required": ["pattern"]},
        fs.glob, mutating=False))
    return reg


__all__ = ["Registry", "Tool", "default_registry", "fs", "shell"]
