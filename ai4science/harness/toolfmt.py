"""Collapsed Claude Code-style tool lines for the NATIVE harness loop.

Mirrors sdk_repl's `⏺ Bash(ls …)` / dim `⎿ …` gutter so both engines look the
same. Native tools use lowercase names and different arg keys (cmd/path/
pattern), hence a separate formatter from sdk_repl._fmt_tool.
"""
from __future__ import annotations

from typing import Optional

_STAR = "⏺"
_ARM = "\x1b[2m  ⎿"      # dim result gutter
_RST = "\x1b[0m"

# Which argument best summarizes a call, per native tool. `pattern` before
# `path` so glob/grep read like Anthropic's `Glob(**/*.py)` (the pattern), not
# the search root.
_KEY_ARGS = ("cmd", "pattern", "path", "file_path", "query", "url",
             "description", "prompt", "name")

# Display the native (lowercase) tool names with Anthropic's capitalization so
# both engines look identical: `⏺ Glob(**/*.py)`, `⏺ Bash(ls -la)`.
_DISPLAY_NAME = {
    "read": "Read", "write": "Write", "edit": "Edit", "bash": "Bash",
    "grep": "Grep", "glob": "Glob",
}


def fmt_tool_start(name: str, args: Optional[dict]) -> str:
    """`⏺ Bash(ls -la)` — one bold collapsed line per tool call."""
    args = args or {}
    arg = next((str(args[k]) for k in _KEY_ARGS
                if isinstance(args.get(k), str) and args[k]), "")
    if not arg:
        arg = next((str(v) for v in args.values()
                    if isinstance(v, str) and v), "")
    arg = arg.replace("\n", " ")
    if len(arg) > 88:
        arg = arg[:85] + "…"
    label = _DISPLAY_NAME.get(name, name)
    return f"{_STAR} \x1b[1m{label}\x1b[0m({arg})"


def fmt_tool_result(result) -> Optional[str]:
    """Dim one-line summary of a tool result: `⎿ first line (+N lines)`."""
    text = str(result or "").strip()
    if not text:
        return None
    lines = text.splitlines()
    first = lines[0][:100]
    tail = f" (+{len(lines) - 1} lines)" if len(lines) > 1 else ""
    err = ("\x1b[31m" if text.startswith(("[blocked]", "[error]")) else "")
    return f"{_ARM} {err}{first}{_RST}\x1b[2m{tail}{_RST}" if err else \
           f"{_ARM} {first}{tail}{_RST}"


def fmt_turn_footer(*, seconds: float, tools: int, tokens: int) -> str:
    """Claude Code-style end-of-turn line: `✶ crunched 12s · 3 tools · 2.2k tokens`."""
    parts = [f"crunched {seconds:.0f}s"]
    if tools:
        parts.append(f"{tools} tool{'s' if tools != 1 else ''}")
    parts.append(f"{round(tokens / 100) / 10:.1f}k tokens" if tokens >= 1000
                 else f"{tokens} tokens")
    return f"\x1b[2m✶ {' · '.join(parts)}{_RST}"
