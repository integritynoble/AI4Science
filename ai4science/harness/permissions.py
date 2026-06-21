from __future__ import annotations

import re
import shlex
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

_SHELL_PUNCT = ";|&<>()"


def _shell_segments(cmd: str):
    """Tokenize *cmd* shell-aware (quotes respected) and split into command
    segments at control operators. Returns None when the command is not
    provably safe to segment (unbalanced quotes, write-redirects, …).

    Redirect rules: `>`/`>>`/`&>` only to /dev/null; `>&` only to fd 1/2;
    `<`/`<<` consume their target as data (reading is fine). Runs of
    punctuation arrive as single tokens (shlex punctuation_chars), so `<(`
    lands here as a control operator and the inner command becomes its own
    segment — validated like any other.
    """
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=_SHELL_PUNCT)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:                      # unbalanced quotes etc.
        return None
    segments: list[list[str]] = []
    cur: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok and all(c in _SHELL_PUNCT for c in tok):
            if ">" in tok:
                nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
                if tok == ">&":
                    if nxt not in ("1", "2"):
                        return None         # >&file writes
                elif nxt != "/dev/null":
                    return None             # any other write target
                i += 2                      # consume the redirect target
                continue
            if set(tok) <= {"<"}:           # < / << read input — consume target
                i += 2
                continue
            if cur:                         # ; | & && || ( ) — segment boundary
                segments.append(cur)
                cur = []
        else:
            cur.append(tok)
        i += 1
    if cur:
        segments.append(cur)
    return segments


def is_read_only_bash(cmd: str) -> bool:
    """True iff every part of *cmd* is provably a read-only inspection."""
    cmd = (cmd or "").strip()
    # Command substitution / backticks can execute anything — reject globally
    # (even quoted: a literal `$(` in a grep pattern is rare; conservative).
    if not cmd or "`" in cmd or "$(" in cmd:
        return False
    segments = _shell_segments(cmd)
    if not segments:
        return False
    for words in segments:
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
        if not path:
            return True, ""
        # MUTATING tools stay sandboxed inside the workspace. Read-only tools
        # (glob/grep/read) may target anywhere — the `path` arg exists precisely
        # to search the machine (e.g. glob path='/home/...'), like Claude Code's
        # Glob/Grep; reading/searching can't damage anything.
        if name in self._mutating:
            target = (self.workspace / path).resolve()
            try:
                target.relative_to(self.workspace)
            except ValueError:
                return False, "sandbox: path escapes the workspace"
        # Protected subdirs (judge/hidden_tests/…) are blocked only for
        # workspace-relative paths, never for an explicit absolute search root.
        if not Path(path).is_absolute():
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


def _syntax_listing(content: str, path: str) -> str:
    """Syntax-highlighted numbered listing (Claude-Code-style), via rich. Falls
    back to a plain numbered listing if rich/lexer is unavailable."""
    try:
        import io
        import shutil
        from rich.console import Console
        from rich.syntax import Syntax
        try:
            lexer = Syntax.guess_lexer(path, content)
        except Exception:
            lexer = "text"
        width = max(40, min(shutil.get_terminal_size((100, 24)).columns, 120))
        # Vivid Monokai palette (like Claude Code) instead of the muted 16-colour
        # ansi_dark. Rendered at 256-colour so it stays vivid on terminals without
        # truecolor (e.g. macOS Terminal.app); rich downsamples Monokai to nearest.
        syn = Syntax(content, lexer, line_numbers=True, theme="monokai",
                     word_wrap=False, background_color="default")
        con = Console(file=io.StringIO(), force_terminal=True,
                      color_system="256", width=width)
        con.print(syn)
        return con.file.getvalue().rstrip("\n")
    except Exception:
        return "\n".join(f"{i:>4}│ {ln}"
                         for i, ln in enumerate(content.splitlines(), 1))


# Keep previews short so the permission question + ALL THREE options (incl. "No")
# stay on screen — a long preview would scroll the menu off. Adapt to the window:
# leave ~11 rows for the header + "Do you want to proceed?" + the 3 options + the
# input line, capped at 12 and never below 4.
def _preview_cap() -> int:
    import shutil
    rows = shutil.get_terminal_size((80, 24)).lines
    return max(4, min(12, rows - 11))


def _cap(text: str, max_lines: int = 0) -> str:
    """Truncate a preview to fit the window, with a dim '+N more lines' note."""
    max_lines = max_lines or _preview_cap()
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    hidden = len(lines) - max_lines
    return "\n".join(lines[:max_lines]) + f"\n\x1b[2m     … (+{hidden} more lines)\x1b[0m"


def _write_preview(path: str, content: str, *, max_lines: int = 0) -> str:
    """Claude-Code-style preview of a file WRITE: a syntax-highlighted numbered
    listing of the content (not a unified diff with '+' on every line). Capped
    short (window-aware) so the permission menu stays visible on small windows."""
    max_lines = max_lines or _preview_cap()
    lines = content.splitlines()
    n = len(lines)
    body = _syntax_listing("\n".join(lines[:max_lines]), path)
    more = f"\n\x1b[2m     … (+{n - max_lines} more lines)\x1b[0m" if n > max_lines else ""
    plural = "" if n == 1 else "s"
    return f"Write {path}  ({n} line{plural})\n{body}{more}"


def _preview(name: str, args: Dict) -> str:
    if name == "bash":
        return f"$ {args.get('cmd', '')}"
    if name == "write":
        # New/overwritten files render as a clean numbered listing — Claude Code
        # parity. (Edits below still show a red/green diff, which is what a diff
        # is good for.)
        return _write_preview(args.get("path", "?"), args.get("content", ""))
    if name == "edit":
        from ai4science.harness.diff import unified_diff
        old = args.get("old", "")
        new = args.get("new", "")
        # Cap the diff too, so a large edit never pushes the menu off screen.
        return _cap(unified_diff(args.get("path", "?"),
                                 old if old.endswith("\n") else old + "\n",
                                 new if new.endswith("\n") else new + "\n"))
    return f"{name} {args}"
