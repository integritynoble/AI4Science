"""Reading the class before doing the work.

Most agents start by attempting the task. This one starts by asking two
questions the task statement usually answers, and which decide how much
autonomy is available at all:

  * **how would I know if this were wrong**, and how soon;
  * **what would it cost to undo**.

From those and the value of a success comes the reliability the class requires,
``p* = rho / (1 + rho)``. This is the number an agent needs and almost never
computes. It is not the evaluator's to choose: a class whose failure costs
thirty times what success is worth demands 0.968, and running it at "usually
fine" is not a judgement call, it is arithmetic nobody did.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

#: Words in a task statement that mean the result leaves the workspace.
#: Deliberately blunt: the cost of over-triggering is a confirmation, and the
#: cost of under-triggering is an irreversible act nobody authorised.
OUTWARD = ("send", "email", "publish", "post", "deploy", "notify", "message",
           "tweet", "announce", "release", "submit to", "push to", "merge to",
           "delete", "drop table", "rm -rf", "charge", "pay", "transfer")

#: Signals that a cheap check already exists, or can be made to exist.
CHECKABLE = ("test", "assert", "verify", "check", "expected", "exactly",
             "must equal", "schema", "criterion", "spec", "rules")


@dataclass(frozen=True)
class Reading:
    """One coordinate, its value, and what evidence produced it.

    The evidence string is not decoration. An estimate with no stated basis
    cannot be argued with, and this one gets used to refuse work.
    """

    value: int          # 0..4
    because: str


@dataclass
class Contract:
    """What the agent believes about the class, before it starts.

    ``p_star`` is the binding output. ``autonomy_justified`` compares it against
    the agent's own calibrated confidence, and where it fails the honest move is
    to escalate rather than to try.
    """

    task_id: str
    verifiability: Reading
    reversibility: Reading
    #: The task as stated. Carried so an executor can be given it verbatim
    #: rather than a paraphrase of it.
    statement: str = ""
    value: float = 1.0
    c_detect: float = 0.0
    c_undo: float = 0.0
    c_residual: float = 0.0
    outward_actions: Tuple[str, ...] = ()
    checks_available: Tuple[str, ...] = ()
    notes: List[str] = field(default_factory=list)

    @property
    def rho(self) -> float:
        return (self.c_detect + self.c_undo + self.c_residual) / max(1e-9, self.value)

    @property
    def p_star(self) -> float:
        r = self.rho
        return 1.0 if math.isinf(r) else r / (1.0 + r)

    @property
    def kappa(self) -> Tuple[int, int]:
        return (self.verifiability.value, self.reversibility.value)

    def autonomy_justified(self, confidence: float) -> Tuple[bool, str]:
        """May this be attempted unattended, at the agent's own confidence?

        The comparison the acceptance ceiling makes unavoidable. An agent that
        is 90% sure may proceed on a class needing 0.5 and may not on a class
        needing 0.97, and the difference is nothing to do with how hard the task
        is.
        """
        if self.p_star >= 1.0:
            return False, ("this class has unbounded residual cost, so no "
                           "attainable reliability delegates it; it needs an "
                           "authorising human, not a better attempt")
        if confidence < self.p_star:
            return False, ("confidence %.2f is below the %.3f this class "
                           "requires (rho=%.2f)" % (confidence, self.p_star, self.rho))
        return True, ""

    def needs_a_check_built_first(self) -> bool:
        """True when nothing here would tell the agent it was wrong."""
        return self.verifiability.value <= 1 and not self.checks_available

    def needs_reversibility_built_first(self) -> bool:
        return self.reversibility.value <= 1 and self.c_residual == 0.0

    def summary(self) -> str:
        return ("class: verifiability=%d (%s), reversibility=%d (%s); "
                "rho=%.2f so p*=%.3f"
                % (self.verifiability.value, self.verifiability.because,
                   self.reversibility.value, self.reversibility.because,
                   self.rho, self.p_star))


def read_task(task_id: str, statement: str, workspace: Optional[Path] = None,
              declared_loss: Optional[Dict[str, float]] = None) -> Contract:
    """Estimate the class from the statement and, where given, the workspace.

    This is deliberately a small amount of evidence and a lot of caution. It is
    not trying to be a good classifier; it is trying to never call an
    irreversible class reversible, because that is the error with no remedy.
    """
    low = statement.lower()
    notes: List[str] = []

    outward = tuple(sorted({w for w in OUTWARD if w in low}))
    checks = tuple(sorted({w for w in CHECKABLE if w in low}))

    # Verifiability. Existing tests in the workspace are the strongest signal
    # there is, because they are a check the agent did not have to invent.
    found_tests: List[str] = []
    if workspace and workspace.exists():
        for p in sorted(workspace.rglob("test_*.py"))[:20]:
            found_tests.append(str(p.relative_to(workspace)))
        for name in ("RULES.md", "SPEC.md", "GOAL.md", "TASK.txt", "QUESTION.txt"):
            if (workspace / name).exists():
                checks = tuple(sorted(set(checks) | {name}))

    if found_tests:
        ver = Reading(4, "a test suite exists in the workspace (%d files)" % len(found_tests))
    elif checks:
        ver = Reading(3, "the statement names a written criterion (%s)" % ", ".join(checks[:3]))
    elif re.search(r"\bexact|\bequal|\bnumber\b|\bcount\b", low):
        ver = Reading(2, "the answer is a value that can be compared")
    else:
        ver = Reading(1, "nothing here says what a correct result looks like")

    # Reversibility. Outward actions are the floor, and the floor is hard.
    if outward:
        rev = Reading(0, "the statement asks for an outward or destructive "
                         "action (%s)" % ", ".join(outward[:3]))
        notes.append("an outward action cannot be undone by verifying it afterwards")
    elif workspace and (workspace / ".git").exists():
        rev = Reading(4, "the workspace is under version control")
    elif workspace is not None:
        rev = Reading(3, "a file workspace that can be snapshotted before work")
    else:
        rev = Reading(2, "no workspace given; assume changes are recoverable but not free")

    d = dict(declared_loss or {})
    c_res = d.get("c_residual", float("inf") if outward else 0.0)
    return Contract(
        task_id=task_id,
        statement=statement,
        verifiability=ver,
        reversibility=rev,
        value=d.get("value", 1.0),
        c_detect=d.get("c_detect", {4: 0.02, 3: 0.1, 2: 0.3, 1: 0.6, 0: 1.0}[ver.value]),
        c_undo=d.get("c_undo", {4: 0.02, 3: 0.1, 2: 0.4, 1: 0.8, 0: 1.5}[rev.value]),
        c_residual=c_res,
        outward_actions=outward,
        checks_available=tuple(found_tests) + checks,
        notes=notes,
    )
