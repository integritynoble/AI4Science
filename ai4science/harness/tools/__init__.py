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
                 shell.bash, mutating=True))
    reg.add(Tool("grep", "Regex search across files.",
                 {"type": "object", "properties": {"pattern": _STR}, "required": ["pattern"]},
                 fs.grep, mutating=False))
    reg.add(Tool("glob", "Glob for files by pattern.",
                 {"type": "object", "properties": {"pattern": _STR}, "required": ["pattern"]},
                 fs.glob, mutating=False))
    return reg


__all__ = ["Registry", "Tool", "default_registry", "fs", "shell"]
