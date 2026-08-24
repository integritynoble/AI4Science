"""Executors behind one protocol, and a competence model that is learned.

Two things follow from taking delegation seriously rather than picking a
favourite model.

**Executors are not interchangeable and should not be assumed equal.** What the
delegation brain needs is ``P(verified success | executor, class)``, estimated
from outcomes an independent verifier produced -- never from the executor's own
account of how it went. A Beta posterior carries its evidence count beside its
mean, so "one success" and "eighty successes" are not reported identically.

**A failure has a kind, and the kind decides what to do next.** Running the same
executor five times is not retrying, it is hoping. This module classifies the
failure and the router acts on the classification: a specification failure means
the contract was bad, a capability failure means the executor was wrong for the
class, and only an execution failure justifies asking the same one again.
"""
from __future__ import annotations

import enum
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from .contract import Contract


class FailureKind(enum.Enum):
    """Why an attempt did not get accepted. The routing depends on this."""

    SPECIFICATION = "specification"   # the criterion was wrong or incomplete
    EXECUTION = "execution"           # a slip; the same executor may fix it
    CAPABILITY = "capability"         # this executor cannot do this class
    ENVIRONMENT = "environment"       # tooling, permission, missing input
    VERIFICATION = "verification"     # the check could not decide

    @property
    def retry_same(self) -> bool:
        return self in (FailureKind.EXECUTION, FailureKind.ENVIRONMENT)


@dataclass
class ExecutionResult:
    confidence: float
    note: str = ""
    cost: float = 1.0
    seconds: float = 0.0


class Executor(Protocol):
    """Anything that can do work: a script, a model, a CLI, another agent."""

    name: str

    def capabilities(self) -> Dict[str, Any]: ...

    def propose_criteria(self, contract: Contract, workspace: Path
                         ) -> Sequence[Tuple[str, str, str]]: ...

    def execute(self, contract: Contract, workspace: Path,
                feedback: Sequence[str]) -> ExecutionResult: ...


class SolverExecutor:
    """Adapter: turns a plain solver into an executor.

    The same shape a Claude Code, Codex, Hermes, OpenClaw or Pi adapter takes.
    The delegation brain never learns which vendor it is talking to -- only what
    that executor's verified success rate is on this class, which is the only
    thing that should decide routing.
    """

    def __init__(self, name: str, solver: Any, cost: float = 1.0,
                 classes: Sequence[str] = ()) -> None:
        self.name = name
        self.solver = solver
        self.cost = cost
        self.classes = tuple(classes)

    def capabilities(self) -> Dict[str, Any]:
        return {"name": self.name, "cost": self.cost,
                "declared_classes": list(self.classes)}

    def propose_criteria(self, contract: Contract, workspace: Path
                         ) -> Sequence[Tuple[str, str, str]]:
        fn = getattr(self.solver, "propose_criteria", None)
        return fn(contract, workspace) if fn else []

    def execute(self, contract: Contract, workspace: Path,
                feedback: Sequence[str]) -> ExecutionResult:
        conf = float(self.solver.attempt(contract, workspace, feedback))
        return ExecutionResult(confidence=conf, cost=self.cost,
                               note="%s pass %d" % (self.name,
                                                    getattr(self.solver, "pass_no", 0)))


def classify_failure(acceptance, feedback: Sequence[str],
                     attempts_by_this_executor: int) -> FailureKind:
    """What kind of failure this was, from evidence rather than from a guess.

    Deliberately conservative in one direction: the second failure of the same
    executor on the same class is called CAPABILITY rather than EXECUTION,
    because an executor that has now failed twice with the failure named for it
    is not having a bad day. That is the rule that stops a retry loop pretending
    to be a strategy.
    """
    if acceptance is None:
        return FailureKind.ENVIRONMENT
    if not acceptance.chain_ok:
        return FailureKind.VERIFICATION
    if not acceptance.results:
        return FailureKind.SPECIFICATION
    detail = " ".join(d for _, ok, d in acceptance.results if not ok).lower()
    if any(w in detail for w in ("no such file", "permission denied",
                                 "command not found", "could not be run")):
        return FailureKind.ENVIRONMENT
    if "timed out" in detail:
        return FailureKind.VERIFICATION
    if attempts_by_this_executor >= 2:
        return FailureKind.CAPABILITY
    return FailureKind.EXECUTION


@dataclass
class Competence:
    """A Beta posterior over one executor's success on one class."""

    executor: str
    class_key: str
    alpha: float = 1.0
    beta: float = 1.0

    def observe(self, success: bool) -> None:
        if success:
            self.alpha += 1.0
        else:
            self.beta += 1.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def evidence(self) -> float:
        return self.alpha + self.beta - 2.0

    def lower(self, z: float = 1.0) -> float:
        """A pessimistic estimate. Routing on the mean over-trusts one success."""
        n = self.alpha + self.beta
        var = (self.alpha * self.beta) / (n * n * (n + 1))
        return max(0.0, self.mean - z * math.sqrt(var))


class CompetenceModel:
    """What each executor has actually been verified to do, per class.

    Updated only from an independent verdict. An executor saying it completed
    the feature is a claim, and a competence model built from claims measures
    confidence rather than capability.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else None
        self.table: Dict[Tuple[str, str], Competence] = {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.table[(r["executor"], r["class"])] = Competence(
                        r["executor"], r["class"], r["alpha"], r["beta"])

    def get(self, executor: str, class_key: str) -> Competence:
        key = (executor, class_key)
        if key not in self.table:
            self.table[key] = Competence(executor, class_key)
        return self.table[key]

    def observe(self, executor: str, class_key: str, success: bool) -> None:
        self.get(executor, class_key).observe(success)
        self.save()

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"executor": c.executor, "class": c.class_key,
                 "alpha": c.alpha, "beta": c.beta}
                for c in sorted(self.table.values(),
                                key=lambda x: (x.executor, x.class_key))]
        self.path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows)
                             + ("\n" if rows else ""), encoding="utf-8")

    def report(self) -> str:
        L = ["%-14s %-22s %7s %9s %s" % ("executor", "class", "P(succ)", "evidence", "")]
        L.append("-" * 62)
        for c in sorted(self.table.values(), key=lambda x: (x.class_key, -x.mean)):
            L.append("%-14s %-22s %7.2f %9.0f" % (c.executor, c.class_key,
                                                  c.mean, c.evidence))
        return "\n".join(L)
