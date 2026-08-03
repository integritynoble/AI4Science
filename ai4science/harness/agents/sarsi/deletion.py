"""The one destructive gate the supervision loop may answer.

A session proving its own reproducibility deleted an artefact and regenerated
it; the `rm` tripped a hook, the loop had no rule, and the task stalled four
passes with nothing wrong with its plan.

The tempting fix — "allow `rm` inside the working directory" — would make the
abstention decorative, because nearly every dangerous delete *is* inside the
directory the agent was given. So the rule is narrow enough to state in one
sentence and to check mechanically:

    a NON-RECURSIVE delete, of NAMED paths that all resolve INSIDE the declared
    working directory, in a command that does NOTHING ELSE, when the owner has
    GRANTED this task permission to delete there.

Every clause carries weight:

  * **non-recursive** — `-r` turns one mistake into all of them.
  * **named paths** — a wildcard's targets are not knowable from the text, and
    approving what cannot be enumerated is approving anything.
  * **inside the root** — the boundary the plan already declares for evidence.
  * **nothing else** — the observed command chained the delete to running a
    script. Approving it would approve the script, and a delete rule that
    approves running scripts is not a delete rule. That command still stops.
  * **granted** — the owner's own permission, through the machinery that
    already exists for permissions. Without it the loop abstains and names the
    grant that would have allowed it.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Iterable, Sequence, Tuple

#: The permission a plan declares, and the owner grants, to allow this at all.
GRANT = "delete files in the working directory"

#: Commands that remove things. `shred` is here to be REFUSED by the recursive
#: and flag checks below — it is named so it cannot slip past as "not a delete".
_DELETERS = {"rm", "unlink", "shred", "rmdir"}

#: Anything that makes the command do more than the delete.
_CHAINS = ("&&", "||", ";", "|", ">", ">>", "<", "&", "$(", "`", "\n")

_RECURSIVE = re.compile(r"^-[a-zA-Z]*[rR]")
_WILDCARD = re.compile(r"[*?\[\]]")


def permitted(command: str, *, root, granted: Iterable[str]) -> Tuple[bool, str]:
    """May the loop press "yes" on this? `(allowed, reason)` — always a reason.

    Refusing is the default and every path out of it is explicit.
    """
    text = (command or "").strip()
    if not text:
        return False, "there is no command to read"

    for token in _CHAINS:
        if token in text:
            return False, ("it does more than delete — this rule answers a "
                           "command that ONLY deletes, because approving a "
                           "chained command approves the other half too")

    try:
        parts = shlex.split(text)
    except ValueError:
        return False, "the command could not be read as a single command"
    if not parts:
        return False, "there is no command to read"

    program = Path(parts[0]).name
    if program not in _DELETERS:
        return False, f"not a delete ({program}) — this rule covers nothing else"
    if program == "shred":
        # It overwrites before unlinking: unrecoverable by design, which is the
        # opposite of the "the session can just make it again" reasoning that
        # justifies answering a delete at all.
        return False, ("shred destroys the contents irrecoverably; that is the "
                       "owner's call, not this loop's")
    if program == "rmdir":
        return False, "removing a directory is the owner's call, not this loop's"

    if GRANT not in set(granted or ()):
        return False, (f"the owner has not granted {GRANT!r} on this task — "
                       f"grant it and it will be answered")

    root_path = Path(root).expanduser().resolve()
    targets = []
    for arg in parts[1:]:
        if arg.startswith("-"):
            if "--no-preserve-root" in arg:
                return False, "--no-preserve-root is never answered here"
            if _RECURSIVE.match(arg):
                return False, ("a recursive delete is never answered here — "
                               "narrow is the point")
            continue
        targets.append(arg)

    if not targets:
        return False, "the command names nothing to delete"

    for target in targets:
        if _WILDCARD.search(target):
            return False, (f"{target!r} is a wildcard — what it would hit "
                           f"cannot be read from the command, and approving "
                           f"what cannot be enumerated approves anything")
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = root_path / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            return False, f"{target!r} could not be resolved"
        if resolved == root_path:
            return False, ("that is the working directory itself; deleting it "
                           "is not working inside it")
        if root_path not in resolved.parents:
            return False, (f"{target!r} is outside the working directory "
                           f"{root_path} — the declared boundary is the whole "
                           f"reason this can be answered at all")

    return True, (f"a non-recursive delete of {', '.join(targets)}, all inside "
                  f"{root_path}, which the owner granted")
