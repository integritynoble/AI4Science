from __future__ import annotations

import difflib


def unified_diff(path: str, old: str, new: str) -> str:
    """A plain unified diff between old and new content for `path`."""
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    )
    return "".join(lines)
