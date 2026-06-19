from __future__ import annotations

import difflib

# Claude-Code-style diff colors (ANSI, matching the rest of the harness).
_GRN = "\x1b[32m"      # additions
_RED = "\x1b[31m"      # deletions
_CYN = "\x1b[36m"      # @@ hunk headers
_DIM = "\x1b[2m"       # file headers
_RST = "\x1b[0m"


def unified_diff(path: str, old: str, new: str, *, color: bool = True) -> str:
    """A unified diff between old and new content for `path`.

    Colorized like Claude Code by default: green additions, red deletions, cyan
    hunk headers, dim file headers. Pass color=False for a plain diff."""
    lines = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    ))
    if not color:
        return "".join(lines)
    out = []
    for ln in lines:
        s = ln.rstrip("\n")
        if ln.startswith(("+++", "---")):
            out.append(f"{_DIM}{s}{_RST}")
        elif ln.startswith("@@"):
            out.append(f"{_CYN}{s}{_RST}")
        elif ln.startswith("+"):
            out.append(f"{_GRN}{s}{_RST}")
        elif ln.startswith("-"):
            out.append(f"{_RED}{s}{_RST}")
        else:
            out.append(s)
    return "\n".join(out)
