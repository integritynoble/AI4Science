"""The criterion register: what "done" means, written before the work exists.

The acceptance ceiling says a result accepted by whatever produced it is an
assertion. The usual response is a rule -- *use an independent verifier* -- and
a rule is a property of the day. This is the mechanism instead.

A criterion is:

  * **registered before the work**, and the register refuses a criterion for a
    deliverable that already exists. A check written after the output is a check
    fitted to it;
  * **write-once and hash-chained**, so an edited criterion is detectable rather
    than merely discouraged;
  * **outside the solver's write set**, enforced by file mode where the platform
    allows and by chain verification always, because permissions can be wrong
    and a hash cannot.

The register also measures the thing nobody measures: **sigma**, the share of
acceptance criteria the agent wrote for itself. Self-authored criteria are not
forbidden -- at any level above instruction-following most of them must be --
but they are counted, and a run whose criteria are all its own is reported as
what it is.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class RegisterViolation(RuntimeError):
    """An attempt to write acceptance after the fact, or to edit it."""


@dataclass(frozen=True)
class Criterion:
    """One check, and who wrote it."""

    name: str
    #: A shell command, or "python:<module>:<function>", run by the acceptor.
    check: str
    #: What the check establishes, and what it does not. Required, for the same
    #: reason a benchmark verifier must state it: an unstated blind spot is a
    #: false-pass rate reported as zero.
    covers: str
    #: "human" if it came with the task, "agent" if the agent derived it.
    author: str
    #: Deliverable this is about, relative to the workspace.
    about: str = ""
    registered_at: float = 0.0
    prev_hash: str = ""

    def digest(self) -> str:
        payload = json.dumps({
            "name": self.name, "check": self.check, "covers": self.covers,
            "author": self.author, "about": self.about,
            "registered_at": round(self.registered_at, 6),
            "prev_hash": self.prev_hash,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_row(self) -> Dict[str, Any]:
        d = {
            "name": self.name, "check": self.check, "covers": self.covers,
            "author": self.author, "about": self.about,
            "registered_at": round(self.registered_at, 6),
            "prev_hash": self.prev_hash,
        }
        d["hash"] = self.digest()
        return d


class CriterionRegister:
    """Append-only, hash-chained, and read-only to whoever is doing the work."""

    def __init__(self, path: Path, workspace: Optional[Path] = None) -> None:
        self.path = Path(path)
        self.workspace = Path(workspace) if workspace else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")
        self._sealed = False

    # -- reading -----------------------------------------------------------

    def rows(self) -> List[Dict[str, Any]]:
        text = self.path.read_text(encoding="utf-8")
        return [json.loads(l) for l in text.splitlines() if l.strip()]

    def criteria(self) -> List[Criterion]:
        out = []
        for r in self.rows():
            out.append(Criterion(
                name=r["name"], check=r["check"], covers=r["covers"],
                author=r["author"], about=r.get("about", ""),
                registered_at=r.get("registered_at", 0.0),
                prev_hash=r.get("prev_hash", "")))
        return out

    @property
    def head(self) -> str:
        rows = self.rows()
        return rows[-1]["hash"] if rows else ""

    def sigma(self) -> float:
        """Share of criteria the agent wrote for itself.

        Rises with the level by construction. Reported, never silently allowed
        to reach one.
        """
        rows = self.rows()
        if not rows:
            return 0.0
        return sum(1 for r in rows if r["author"] == "agent") / len(rows)

    # -- writing -----------------------------------------------------------

    def register(self, name: str, check: str, covers: str, author: str = "agent",
                 about: str = "", now: Optional[float] = None) -> Criterion:
        if self._sealed:
            raise RegisterViolation(
                "the register is sealed; the work has started. A criterion "
                "added now would be a criterion fitted to the result.")
        if not covers.strip():
            raise RegisterViolation(
                "%r has no `covers`: a check that does not say what it misses "
                "reports its false-pass rate as zero." % name)
        if any(r["name"] == name for r in self.rows()):
            raise RegisterViolation(
                "%r is already registered, and this register is write-once. "
                "Register a new criterion; do not move the old one." % name)
        if about and self.workspace and (self.workspace / about).exists():
            raise RegisterViolation(
                "%s already exists in the workspace, so a criterion about it "
                "cannot be pre-registered. This is the check that stops "
                "acceptance being written around a result." % about)

        c = Criterion(name=name, check=check, covers=covers, author=author,
                      about=about, registered_at=now if now is not None else time.time(),
                      prev_hash=self.head)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(c.to_row(), sort_keys=True) + "\n")
        return c

    def seal(self) -> str:
        """Close the register. Everything after this is execution.

        Also drops the file to read-only. The mode is a courtesy -- an agent
        running as the same user can undo it -- which is exactly why
        :meth:`verify_chain` exists and is what the acceptor actually trusts.
        """
        self._sealed = True
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            pass
        return self.head

    # -- the check that does not depend on the file system -----------------

    def verify_chain(self) -> Tuple[bool, str]:
        """Recompute the chain. Any edit anywhere breaks it from that point on."""
        prev = ""
        for i, r in enumerate(self.rows()):
            c = Criterion(name=r["name"], check=r["check"], covers=r["covers"],
                          author=r["author"], about=r.get("about", ""),
                          registered_at=r.get("registered_at", 0.0),
                          prev_hash=r.get("prev_hash", ""))
            if c.prev_hash != prev:
                return False, ("criterion %d (%s) does not follow the one before "
                               "it; the register has been reordered or spliced"
                               % (i, r["name"]))
            if c.digest() != r.get("hash"):
                return False, ("criterion %d (%s) has been edited since it was "
                               "registered" % (i, r["name"]))
            prev = r["hash"]
        return True, ""
