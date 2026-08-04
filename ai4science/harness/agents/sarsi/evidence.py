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

  * **it never leaves the evidence root.** That root is the task's own folder,
    or the `Working directory:` the plan **declared** — declared, because a
    criterion naming `/etc/passwd` must not be able to move it. A path outside
    is reported as outside and not read; it is never silently dropped, because
    silence about a file the owner named reads as "nothing to report".
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
    """The evidence a verdict should rest on, read from `folder` and only there.

    `folder` is the task's **evidence root**: its own directory by default, or
    the `Working directory:` the plan declared. Declared is the whole point —
    the boundary moves when the plan says so, never because a criterion names a
    path.
    """
    roots = ([Path(f).expanduser().resolve() for f in folder]
             if isinstance(folder, (list, tuple, set))
             else [Path(folder).expanduser().resolve()])
    parts: List[str] = []
    for root in roots:
        parts.extend(_from_root(root, criteria))

    text = "\n\n".join(p for p in parts if p)
    return _with_pane(text, screen)


def _from_root(root, criteria: Sequence[str]) -> List[str]:
    parts: List[str] = []
    if not root.is_dir():
        # NOT an empty listing. "the folder is empty" and "the folder is not
        # there" are different facts, and the first is far more damning.
        parts.append(f"THE WORKING DIRECTORY {root} does not exist, so nothing "
                     f"could be read from it")
    else:
        listing = _listing(root)
        if listing:
            parts.append(f"FILES IN {root} (real listing):\n" + listing)

    for name in named_files(criteria):
        parts.append(_read(root, name))
    return parts


def _with_pane(text: str, screen: str) -> str:
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
    # An absolute path is taken as itself — the containment check below decides
    # whether it may be read. `root / "/etc/passwd"` would silently BECOME
    # /etc/passwd, so joining first and checking after is the only safe order.
    target = Path(name) if Path(name).is_absolute() else (root / name)
    try:
        resolved = target.resolve()
    except OSError:
        return f"{name}: could not be resolved"

    # Never outside the root — a criterion is not a licence to read. Checked on
    # the RESOLVED path, so a symlink planted inside the root cannot widen it.
    if resolved != root and root not in resolved.parents:
        return (f"{name}: outside {root}, so it was not read "
                f"(evidence is gathered from the declared working directory "
                f"only)")

    if not resolved.exists():
        # absence, stated. Silence here would read as "nothing to report".
        return f"{name}: NOT PRESENT in {root}"
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
