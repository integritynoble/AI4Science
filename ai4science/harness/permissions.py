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


# ── Read-only bash classification (Claude Code parity) ──────────────────────
# Commands that only inspect state. A command classified read-only skips the
# [y/N] confirmation and runs even in /readonly mode — same as Claude Code's
# auto-allow for reads / plan mode. The classifier is CONSERVATIVE: anything
# it can't prove read-only (quoted separators, unknown binaries, redirects)
# falls through to the normal confirm gate. False-negatives prompt; never the
# reverse.

_READ_ONLY_CMDS = frozenset({
    "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "find",
    "wc", "file", "stat", "du", "df", "pwd", "echo", "printf", "which",
    "whereis", "type", "uname", "whoami", "id", "date", "hostname", "nproc",
    "free", "uptime", "ps", "printenv", "sort", "uniq", "cut", "tr", "diff",
    "cmp", "column", "nl", "jq", "md5sum", "sha1sum", "sha256sum", "b2sum",
    "cksum", "basename", "dirname", "realpath", "readlink", "tree", "git",
})

# git subcommands that never mutate, regardless of arguments.
_READ_ONLY_GIT = frozenset({
    "status", "log", "diff", "show", "ls-files", "rev-parse", "blame",
    "shortlog", "describe", "reflog", "grep",
})

# find actions that write or execute.
_FIND_MUTATORS = frozenset({
    "-delete", "-exec", "-execdir", "-ok", "-okdir",
    "-fprint", "-fprintf", "-fls",
})

# Redirects to /dev/null (and stderr merges) are harmless; strip them before
# rejecting on any remaining redirect character.
_DEVNULL_REDIRECT = re.compile(r"[0-9]*>{1,2}\s*/dev/null|2>&1")

# Splitting on every separator (incl. quoted ones) is deliberately lossy in
# the conservative direction: a quoted `;` produces a bogus extra segment
# whose first word won't be allowlisted, so the command just falls back to
# the confirm prompt.
_SEGMENT_SPLIT = re.compile(r"[;|&\n]+")


def is_read_only_bash(cmd: str) -> bool:
    """True iff every part of *cmd* is provably a read-only inspection."""
    cmd = (cmd or "").strip()
    if not cmd:
        return False
    stripped = _DEVNULL_REDIRECT.sub(" ", cmd)
    # Command substitution, process substitution, or any remaining redirect
    # can write or execute — not provably read-only.
    if any(tok in stripped for tok in ("$(", "`", "<(", ">(", ">")):
        return False
    for segment in _SEGMENT_SPLIT.split(stripped):
        words = segment.split()
        if not words:
            continue
        prog = words[0]
        if prog not in _READ_ONLY_CMDS:
            return False
        if prog == "git":
            if len(words) < 2 or words[1] not in _READ_ONLY_GIT:
                return False
        elif prog == "find":
            if any(w in _FIND_MUTATORS for w in words[1:]):
                return False
        elif prog == "sort":
            if "-o" in words[1:]:
                return False
    return True


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
            # Read-only commands skip confirmation and run even in /readonly
            # mode (Claude Code parity). The sandbox check above still wins.
            if is_read_only_bash(args.get("cmd", "")):
                return True, ""
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
