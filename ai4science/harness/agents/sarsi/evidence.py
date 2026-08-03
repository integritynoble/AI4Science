"""Gathering evidence, rather than photographing a terminal.

The live run that forced this: the session had written `report.md` correctly,
the pane showed a spinner and some narration about the harness, and the verifier
answered — accurately — *"the visible pane contains no `ls`/`cat`/`grep` output
for report.md."* It was being asked to judge a screenshot of someone talking
about the work.

A terminal pane is where a session **says** what it did. Evidence is what it
**left behind**. So this collects, on purpose:

  * a real listing of the task folder;
  * the real contents of the files the **criteria name**;
  * and a named file's **absence**, stated — because a file that should exist
    and does not is the most useful evidence there is, and silence about it
    reads as "nothing to report".

Two refusals, not filters:

  * **it never leaves the task folder.** Criteria start owner-written and are
    polished by a model, so a criterion naming `/etc/passwd` reads nothing.
  * **it runs nothing.** It reads. Evidence gathering that could execute would
    be a second, ungoverned path to running commands, next door to the one the
    governance hook exists to watch.

The pane is still included, because a session's own account is worth having —
but **labelled as narration**, and placed after the facts, so a claim on a
screen can never be mistaken for the thing it claims.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence

MAX_FILE_CHARS = 8000
MAX_TOTAL_CHARS = 32000
MAX_PANE_CHARS = 4000

#: Something that looks like a filename inside a criterion.
_FILENAME = re.compile(r"[\w./\\-]+\.[A-Za-z0-9]{1,8}")

#: Files worth reading as text. Anything else is listed and left alone.
_TEXTISH = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".py", ".sh",
            ".log", ".html", ".toml", ".ini", ".cfg", ".rst", ".tsv"}


def named_files(criteria: Iterable[str]) -> List[str]:
    """The filenames the criteria mention, in order, without duplicates."""
    out: List[str] = []
    for criterion in criteria or []:
        for hit in _FILENAME.findall(criterion or ""):
            if hit not in out:
                out.append(hit)
    return out


def gather(folder, criteria: Sequence[str], screen: str = "") -> str:
    """The evidence a verdict should rest on."""
    root = Path(folder).resolve()
    parts: List[str] = []

    listing = _listing(root)
    if listing:
        parts.append("FILES IN THE TASK FOLDER (real listing):\n" + listing)

    for name in named_files(criteria):
        parts.append(_read(root, name))

    text = "\n\n".join(p for p in parts if p)

    pane = (screen or "").strip()
    if pane:
        # last, and named for what it is: what the session SAID
        text += ("\n\nWHAT THE SESSION SAID (narration — not evidence; a claim "
                 "on a screen is not the thing it claims):\n"
                 + pane[-MAX_PANE_CHARS:])

    if len(text) > MAX_TOTAL_CHARS:
        text = text[:MAX_TOTAL_CHARS] + "\n… [truncated]"
    return text


def _listing(root: Path) -> str:
    if not root.is_dir():
        return ""
    rows = []
    for child in sorted(root.iterdir()):
        try:
            size = child.stat().st_size
        except OSError:
            continue
        kind = "dir " if child.is_dir() else "file"
        rows.append(f"  {kind} {size:>9} bytes  {child.name}")
    return "\n".join(rows) if rows else "  (no files)"


def _read(root: Path, name: str) -> str:
    target = (root / name)
    try:
        resolved = target.resolve()
    except OSError:
        return f"{name}: could not be resolved"

    # never outside the task folder — a criterion is not a licence to read
    if resolved != root and root not in resolved.parents:
        return (f"{name}: outside the task folder, so it was not read "
                f"(evidence is gathered from the task's own folder only)")

    if not resolved.exists():
        # absence, stated. Silence here would read as "nothing to report".
        return f"{name}: NOT PRESENT in the task folder"
    if resolved.is_dir():
        return f"{name}: is a directory"
    if resolved.suffix.lower() not in _TEXTISH:
        return f"{name}: present ({resolved.stat().st_size} bytes), not read as text"

    try:
        body = resolved.read_text(errors="replace")
    except OSError as e:
        return f"{name}: present but unreadable ({type(e).__name__})"
    truncated = ""
    if len(body) > MAX_FILE_CHARS:
        body, truncated = body[:MAX_FILE_CHARS], "\n… [truncated]"
    return f"CONTENTS OF {name} (read from disk):\n{body}{truncated}"
