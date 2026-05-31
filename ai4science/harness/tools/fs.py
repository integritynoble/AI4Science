from __future__ import annotations

import fnmatch
import os
from pathlib import Path


def read(workspace: Path, *, path: str) -> str:
    p = (workspace / path)
    text = p.read_text()
    lines = text.splitlines()
    return "\n".join(f"{i+1}\t{ln}" for i, ln in enumerate(lines))


def write(workspace: Path, *, path: str, content: str) -> str:
    p = (workspace / path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} bytes to {path}"


def edit(workspace: Path, *, path: str, old: str, new: str) -> str:
    p = (workspace / path)
    text = p.read_text()
    count = text.count(old)
    if count == 0:
        raise ValueError(f"old string not found in {path}")
    if count > 1:
        raise ValueError(f"old string is not unique in {path} ({count} matches)")
    p.write_text(text.replace(old, new, 1))
    return f"edited {path}"


def glob(workspace: Path, *, pattern: str) -> str:
    hits = []
    for root, _dirs, files in os.walk(workspace):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), workspace)
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(f, pattern):
                hits.append(rel)
    return "\n".join(sorted(hits))


def grep(workspace: Path, *, pattern: str) -> str:
    import re
    rx = re.compile(pattern)
    out = []
    for root, _dirs, files in os.walk(workspace):
        for f in files:
            fp = Path(root) / f
            try:
                for i, ln in enumerate(fp.read_text().splitlines()):
                    if rx.search(ln):
                        out.append(f"{os.path.relpath(fp, workspace)}:{i+1}:{ln}")
            except (UnicodeDecodeError, OSError):
                continue
    return "\n".join(out)
