"""`WRT` — may the loop answer a write gate? Only inside what was declared.

Every live run today ended the same way: correct work, and the loop stopped at

    Create file
    /home/grace/live-final/win.md
    Do you want to create win.md?
    ❯ 1. Yes
      2. Yes, allow all edits in live-final/ during this session
      3. No

That directory is the one the task declared. The owner granted the permissions
its plan named and `release` raised the ceiling. `blast` already treats those
paths as *paths the task is allowed to write*, and the sandbox already permits
them — `PermissionGate` allows `[workspace] + writable_roots`, filled from the
same list. The only thing still asking is Claude Code's hook, and what it is
asking for is a decision the owner has already made.

So the loop is not inventing authority here; it is applying authority that
exists. That is the same argument that lets it answer one delete, and this is
built to the same rule as `deletion.permitted`:

    **Refusing is the default, and every path out of it is explicit.**

Four refusals carry the weight:

  * **outside the declared roots**, compared as resolved paths — `/x/work-evil`
    shares six characters with `/x/work` and is not inside it;
  * **before release**, because the ceiling is still A0 and nothing has been
    granted, so there is no authority to apply;
  * **a path the gate does not state in full** — the question line says
    `create summary.md?`, and live that basename belonged to
    `../../../../../live-retire/summary.md`. A file located by guessing is a
    file approved by guessing;
  * **the wider option** — *"allow all edits during this session"* is a standing
    grant over everything that follows, which is not what the owner gave and
    not this loop's to take.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

#: The narrow yes. Never the option that also says "and allow all …".
ANSWER = "1"

#: Claude Code's block header above the path it is about to write. Matched as a
#: whole line: prose merely containing the word "edit" is not this.
_HEADER = re.compile(r"^\s*(Create|Edit|Update|Write)\s+file\s*$",
                     re.M | re.I)

#: The option the loop must never press, wherever it appears.
_STANDING = re.compile(r"allow all edits|don'?t ask again|and stop asking",
                       re.I)

#: `❯ 1. …` — the option `ANSWER` would actually press.
_FIRST_OPTION = re.compile(r"^\s*❯?\s*1\.\s*(?P<text>.+?)\s*$", re.M)


def _stated_path(screen: str) -> Tuple[Optional[str], str]:
    """The one path this gate names in full, or a reason there isn't one."""
    lines = (screen or "").splitlines()
    found: List[str] = []
    for i, line in enumerate(lines):
        if not _HEADER.match(line):
            continue
        # The path is the next non-empty line. Taken positionally rather than
        # by pattern: a filename can look like anything, and a pattern loose
        # enough to match them all would match prose too.
        for nxt in lines[i + 1:]:
            if nxt.strip():
                found.append(nxt.strip())
                break
    if not found:
        return None, ("this gate does not state which file in full — the "
                      "question line names a basename, and a file located by "
                      "guessing is a file approved by guessing")
    if len(set(found)) > 1:
        return None, (f"it names {len(set(found))} files; if it cannot be read "
                      f"as one write it is not read at all")
    return found[0], ""


def permitted(screen: str, *, roots: Sequence, cwd, released: bool
              ) -> Tuple[bool, str]:
    """May the loop press `ANSWER` on this write gate? `(allowed, reason)`."""
    if not released:
        return False, ("this task has not been released — the ceiling is still "
                       "A0 and nothing has been granted, so there is no "
                       "authority here to apply")

    declared = []
    for root in (roots or ()):
        try:
            declared.append(Path(root).expanduser().resolve())
        except OSError:
            continue
    if not declared:
        return False, ("this task declares no paths, so there is no boundary "
                       "that would make a write answerable")

    # Checked BEFORE the path: if option 1 is the standing grant, pressing it
    # takes a permission over everything that follows no matter which file this
    # particular gate is about.
    first = _FIRST_OPTION.search(screen or "")
    if first is None:
        return False, "no option is offered that this could press"
    if _STANDING.search(first.group("text")):
        return False, ("the first option is a standing grant for the rest of "
                       "the session; that is the owner's to give, not this "
                       "loop's to take")

    stated, why = _stated_path(screen)
    if stated is None:
        return False, why

    candidate = Path(stated).expanduser()
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    try:
        target = candidate.resolve()
    except OSError:
        return False, f"{stated!r} could not be resolved"

    for root in declared:
        if target == root:
            break                     # the directory itself, not a file in it
        if root in target.parents:
            return True, (f"a write to {target}, inside the declared "
                          f"{root} the owner released")
    return False, (f"{stated!r} is outside the declared paths "
                   f"({', '.join(str(d) for d in declared)}) — that boundary "
                   f"is the whole reason this can be answered at all")
