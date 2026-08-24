"""Delegation compression: lowering the cost of checking, once, for good.

Solving a class repeatedly turns a hard class into an easy one -- but only if
something is left behind. The observation that makes this the centre rather than
a footnote:

    Capability improvements raise the success rate *within* a class.
    Compression moves the class.

An agent that gets better at cleaning data raises its own rate on that class.
An agent that writes the check for cleaned data has moved the class's
verifiability, which raises the sustainable delegation grade for every future
run and for every other agent working the same class. The second compounds and
the first does not.

So after a class is accepted, the harness emits the artifact that will check it
next time, and records the movement in kappa it expects. The claim is
falsifiable: run the class again and see whether the check fires.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .criterion import Criterion


@dataclass
class Compression:
    """What was left behind, and what it is expected to move."""

    class_key: str
    artifact: str                 # path, relative to the library
    kind: str                     # "check" | "tool" | "procedure"
    moves: str                    # which coordinate, and from what to what
    from_criteria: Tuple[str, ...] = ()

    def to_row(self) -> Dict[str, object]:
        return {"class": self.class_key, "artifact": self.artifact,
                "kind": self.kind, "moves": self.moves,
                "from_criteria": list(self.from_criteria)}


class Library:
    """Where compressions accumulate. Reused across runs; that is the point."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = self.root / "index.jsonl"
        if not self.index.exists():
            self.index.write_text("", encoding="utf-8")

    def rows(self) -> List[Dict[str, object]]:
        return [json.loads(l) for l in self.index.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    def known(self, class_key: str) -> List[Dict[str, object]]:
        """Checks this library already holds for a class.

        Consulted *before* work starts. A class the library covers is a class
        that arrives already verifiable, which is the whole return on having
        done it once.
        """
        return [r for r in self.rows() if r["class"] == class_key]

    def compress(self, class_key: str, criteria: Sequence[Criterion]) -> Optional[Compression]:
        """Turn the criteria that just accepted a result into a reusable check."""
        usable = [c for c in criteria if c.check.startswith("pycode:")]
        if not usable:
            return None
        name = "check_%s.py" % class_key.replace(".", "_").replace("#", "_")
        path = self.root / name
        body = ['"""Emitted by delegation compression after %s was accepted.' % class_key,
                "",
                "Each function below is a criterion that held. Running this on a",
                "future attempt is what makes the class cheap to check, which is",
                "the only route by which an agent raises its own frontier.",
                '"""',
                "import sys", "", "_failed = []", ""]
        for i, c in enumerate(usable):
            src = c.check[len("pycode:"):]
            body.append("def _c%d():" % i)
            body.append("    # covers: %s" % c.covers.replace("\n", " "))
            for line in src.splitlines():
                body.append("    " + line)
            body.append("")
            body.append("try:")
            body.append("    _c%d()" % i)
            body.append("except Exception as e:")
            body.append("    _failed.append(%r + ': ' + str(e))" % c.name)
            body.append("")
        body += ["for f in _failed:", "    print('FAIL: ' + f)",
                 "sys.exit(1 if _failed else 0)"]
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        path.chmod(0o755)

        comp = Compression(
            class_key=class_key, artifact=name, kind="check",
            moves="verifiability: this class now arrives with a check that did "
                  "not exist before, so the next attempt is checkable without "
                  "inventing one",
            from_criteria=tuple(c.name for c in usable))
        if not any(r["artifact"] == name for r in self.rows()):
            with self.index.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(comp.to_row(), sort_keys=True) + "\n")
        return comp
