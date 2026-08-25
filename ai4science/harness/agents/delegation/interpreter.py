"""Finding a Python to run a criterion with, including inside a frozen binary.

``sys.executable`` is the obvious answer and is wrong exactly where it matters.
In a PyInstaller one-file build it points at the agent binary, so a criterion
launched with it re-invokes the agent with a script path as its argument. Every
check then fails, for a reason that has nothing to do with the work -- and a
verifier that cannot pass correct work is indistinguishable from a strict one.

So: use ``sys.executable`` when it really is an interpreter, otherwise look for
one on PATH, and if there is none, say so. A missing interpreter makes a
criterion **undecidable**, which is a different outcome from failed and is
reported as such -- an agent that treats "I could not check" as "it is wrong"
will retry work that was already correct.
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import Optional, Tuple

CANDIDATES = ("python3", "python3.12", "python3.11", "python3.10", "python")


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def find() -> Tuple[Optional[str], str]:
    """(path to an interpreter, why) -- path is None when there is none."""
    if not frozen():
        return sys.executable, "the running interpreter"
    for name in CANDIDATES:
        p = shutil.which(name)
        if p:
            return p, "found %r on PATH (this build is frozen, so " \
                      "sys.executable is the binary itself)" % name
    return None, ("no Python interpreter on PATH. This binary runs its "
                  "acceptance checks in a separate process and needs one; "
                  "without it a result can be produced but not accepted, and "
                  "an unaccepted result is not a completed task.")
