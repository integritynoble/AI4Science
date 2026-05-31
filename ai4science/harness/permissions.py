from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

PROTECTED_DIRS = ("judge", "hidden_tests")

_BASH_BLOCK = re.compile(
    r"(^|[\s=:/;|&])(\.\./)"        # parent-directory escape (incl. ;|& chained, no space)
    r"|(^|[\s=:/;|&'\"])(" + "|".join(PROTECTED_DIRS) + r")/"   # judge/ or hidden_tests/
)


def _bash_cmd_safe(cmd: str) -> tuple:
    """Heuristic guard: block shell commands that reference protected dirs or
    escape the workspace. NOT airtight against deliberate obfuscation (documented)."""
    if _BASH_BLOCK.search(cmd or ""):
        return False, "sandbox: bash command references a protected/parent path"
    return True, ""


class SandboxError(Exception):
    pass


class PermissionGate:
    """Decides whether a tool call may run. Mirrors Claude Code's modes."""

    def __init__(self, *, workspace: Path, read_only: bool, auto_yes: bool,
                 confirm: Optional[Callable[[str, Dict, str], bool]] = None) -> None:
        self.workspace = workspace.resolve()
        self.read_only = read_only
        self.auto_yes = auto_yes
        self.confirm = confirm
        self._mutating = {"write", "edit", "bash"}

    def _sandbox_ok(self, name: str, args: Dict) -> Tuple[bool, str]:
        path = args.get("path")
        if path:
            target = (self.workspace / path).resolve()
            try:
                target.relative_to(self.workspace)
            except ValueError:
                return False, "sandbox: path escapes the workspace"
            parts = Path(path).parts
            if parts and parts[0] in PROTECTED_DIRS:
                return False, f"sandbox: '{parts[0]}/' is protected"
        return True, ""

    def allow(self, name: str, args: Dict) -> Tuple[bool, str]:
        sok, sreason = self._sandbox_ok(name, args)
        if not sok:
            return False, sreason
        if name == "bash":
            bok, breason = _bash_cmd_safe(args.get("cmd", ""))
            if not bok:
                return False, breason
        if name not in self._mutating:
            return True, ""
        if self.read_only:
            return False, "read-only mode: mutating tools are blocked"
        if self.auto_yes:
            return True, ""
        if self.confirm is None:
            return False, "no confirmation handler available"
        preview = _preview(name, args)
        return bool(self.confirm(name, args, preview)), "user decision"


def _preview(name: str, args: Dict) -> str:
    if name == "bash":
        return f"$ {args.get('cmd', '')}"
    if name == "write":
        from ai4science.harness.diff import unified_diff
        return unified_diff(args.get("path", "?"), "", args.get("content", ""))
    if name == "edit":
        from ai4science.harness.diff import unified_diff
        old = args.get("old", "")
        new = args.get("new", "")
        return unified_diff(args.get("path", "?"),
                            old if old.endswith("\n") else old + "\n",
                            new if new.endswith("\n") else new + "\n")
    return f"{name} {args}"
