"""Making the work undoable before doing it.

Verification tells you that you were wrong. Reversibility decides whether it
matters. They are different properties and conflating them is the common error:
a task that is cheap to check and impossible to undo is worse than one that is
expensive to check and trivially undone.

So the harness snapshots before it mutates, and gates anything it cannot undo.
The gate is not advice. An action classified irreversible does not run without
an explicit authorisation, because verification after the fact is not a remedy
and no amount of care converts it into one.
"""
from __future__ import annotations

import enum
import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple


class Reversibility(enum.IntEnum):
    FREE = 3          # a snapshot restores it exactly
    CHEAP = 2         # one command, or a rerun
    COSTLY = 1        # possible, but it costs something real
    NONE = 0          # it has left the building


@dataclass
class Step:
    what: str
    reversibility: Reversibility
    snapshot: Optional[str] = None
    authorised_by: str = ""
    done: bool = False
    note: str = ""


class UndoLedger:
    """Snapshots a workspace, and refuses what it cannot take back."""

    def __init__(self, workspace: Path, store: Path) -> None:
        self.workspace = Path(workspace)
        self.store = Path(store)
        self.store.mkdir(parents=True, exist_ok=True)
        self.steps: List[Step] = []
        self._n = 0

    def snapshot(self, label: str = "") -> str:
        """Copy the workspace aside. This is the cheap half of delegation."""
        self._n += 1
        sid = "snap%03d%s" % (self._n, ("-" + label) if label else "")
        dst = self.store / sid
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(self.workspace, dst, dirs_exist_ok=True)
        return sid

    def restore(self, sid: str) -> None:
        src = self.store / sid
        if not src.exists():
            raise FileNotFoundError("no snapshot %r" % sid)
        for p in sorted(self.workspace.iterdir()):
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        shutil.copytree(src, self.workspace, dirs_exist_ok=True)

    def gate(self, step: Step, authorisation: Optional[str] = None) -> Tuple[bool, str]:
        """May this run unattended?

        ``FREE`` and ``CHEAP`` proceed after a snapshot. ``COSTLY`` proceeds only
        with a snapshot that actually covers it. ``NONE`` never proceeds
        unattended, at any capability -- that is the floor, not a caution.
        """
        if step.reversibility >= Reversibility.CHEAP:
            step.snapshot = step.snapshot or self.snapshot(step.what[:12].replace(" ", "_"))
            self.steps.append(step)
            return True, ""
        if step.reversibility == Reversibility.COSTLY:
            if authorisation:
                step.authorised_by = authorisation
                step.snapshot = step.snapshot or self.snapshot("costly")
                self.steps.append(step)
                return True, ""
            return False, ("%r is recoverable but not cheaply; it needs an "
                           "authorisation, which is a governance question and "
                           "not a cognitive one" % step.what)
        if not authorisation:
            self.steps.append(step)
            return False, ("%r cannot be undone. No verification substitutes, "
                           "because verification after the fact is not a remedy. "
                           "This needs a human to authorise, and that is a floor "
                           "no capability removes." % step.what)
        step.authorised_by = authorisation
        self.steps.append(step)
        return True, ""

    def summary(self) -> Dict[str, int]:
        out = {r.name.lower(): 0 for r in Reversibility}
        for s in self.steps:
            out[s.reversibility.name.lower()] += 1
        out["snapshots"] = self._n
        return out
