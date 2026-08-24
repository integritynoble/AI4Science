"""The loop. Class first, check second, snapshot third, work fourth.

Most agent loops are: attempt, observe, repeat. This one spends its first moves
on the two properties that decide how much autonomy is available at all, and
only then does the work:

    read the class  ->  is the reliability it needs attainable?
                        no  -> escalate; that is the answer, not a failure
                        yes -> continue
                    ->  is there a check?   no  -> build one, and register it
                    ->  is it reversible?   no  -> snapshot, or gate it
                    ->  seal the register   (everything after this is execution)
                    ->  attempt   (the solver; it never sees the register)
                    ->  accept    (another process, running what was registered)
                        fail -> restore, replan, retry within budget
                    ->  compress  (leave the check behind for next time)

The solver is a parameter. That is the claim: delegation is a property of this
loop, not of whatever is inside the ``attempt`` box, and the same solver placed
in and out of it should sit at different points on the frontier.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from .acceptor import Acceptance, accept
from .compress import Compression, Library
from .contract import Contract, read_task
from .criterion import Criterion, CriterionRegister, RegisterViolation
from .escalate import Escalation, cheapest_question, rather_ask_than_guess
from .executor import (CompetenceModel, Executor, ExecutionResult, FailureKind,
                       SolverExecutor, classify_failure)
from .reversible import Reversibility, Step, UndoLedger
from .router import Choice, Router


class Solver(Protocol):
    """Whatever actually does the work. A script, a model, a CLI."""

    def propose_criteria(self, contract: Contract, workspace: Path
                         ) -> Sequence[Tuple[str, str, str]]:
        """(name, check, covers) triples, derived from the task statement only."""

    def attempt(self, contract: Contract, workspace: Path, feedback: Sequence[str]
                ) -> float:
        """Do the work in ``workspace``. Return calibrated confidence 0..1."""


@dataclass
class Outcome:
    task_id: str
    accepted: bool
    attempts: int
    escalations: List[Escalation] = field(default_factory=list)
    #: (executor, FailureKind) per failed attempt, in order.
    route: List[Tuple[str, str]] = field(default_factory=list)
    acceptance: Optional[Acceptance] = None
    contract: Optional[Contract] = None
    compression: Optional[Compression] = None
    refused: str = ""
    trace: List[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def max_cid(self) -> int:
        return max((e.cid for e in self.escalations), default=0)

    @property
    def sigma(self) -> float:
        return self.acceptance.sigma if self.acceptance else 0.0

    def report(self) -> str:
        L = ["task: %s" % self.task_id]
        if self.contract:
            L.append("  " + self.contract.summary())
        L.append("  outcome: %s in %d attempt(s)"
                 % ("ACCEPTED" if self.accepted else
                    ("ESCALATED" if self.escalations and not self.accepted and self.refused
                     else "NOT ACCEPTED"), self.attempts))
        if self.refused:
            L.append("  refused: %s" % self.refused)
        for e in self.escalations:
            L.append("  " + e.as_note())
        L.append("  deepest help: CID%d   sigma: %.2f" % (self.max_cid, self.sigma))
        if self.compression:
            L.append("  compressed: %s (%s)" % (self.compression.artifact,
                                                self.compression.kind))
        return "\n".join(L)


class DelegationAgent:
    """The harness. Wraps a solver; does not replace it."""

    def __init__(self, solver: Optional[Solver] = None,
                 library: Optional[Library] = None,
                 max_attempts: int = 3, human=None,
                 executors: Optional[Sequence[Executor]] = None,
                 competence: Optional[CompetenceModel] = None) -> None:
        # A single solver is the one-executor case of the general one. Keeping
        # both shapes means the harness can be used before there is anything to
        # route between, which is how it will actually be adopted.
        if executors is None:
            if solver is None:
                raise ValueError("give either a solver or a list of executors")
            executors = [SolverExecutor("solver", solver)]
        self.executors: List[Executor] = list(executors)
        self.competence = competence or CompetenceModel()
        self.router = Router(self.executors, self.competence)
        self.library = library
        self.max_attempts = max_attempts
        #: Optional callable answering escalations. Absent means unattended: an
        #: escalation then ends the run, which is the correct H0 behaviour.
        self.human = human

    def run(self, task_id: str, statement: str, workspace: Path,
            store: Path, declared_loss: Optional[Dict[str, float]] = None,
            class_key: Optional[str] = None) -> Outcome:
        t0 = time.time()
        out = Outcome(task_id=task_id, accepted=False, attempts=0)
        ws, store = Path(workspace), Path(store)
        store.mkdir(parents=True, exist_ok=True)

        # 1. Read the class. This is the move most loops skip.
        contract = read_task(task_id, statement, ws, declared_loss)
        out.contract = contract
        out.trace.append(contract.summary())

        # 2. Is the reliability this class demands even reachable?
        if contract.p_star >= 1.0:
            e = cheapest_question(needs_permission=(
                "this class has unbounded residual cost (%s); it needs an "
                "authorisation before anything is done"
                % ", ".join(contract.outward_actions or ("irreversible action",))))
            out.escalations.append(e)
            answer = self.human(e) if self.human else None
            if not answer:
                out.refused = ("irreversible class, unattended: the floor here "
                               "is not capability, it is authority")
                out.seconds = time.time() - t0
                return out
            out.trace.append("authorised: %s" % answer)

        # 3. A check, registered before the work exists.
        register = CriterionRegister(store / "criteria.jsonl", workspace=ws)
        if self.library:
            for row in self.library.known(class_key or task_id.split("#")[0]):
                try:
                    register.register(
                        name="library:%s" % row["artifact"],
                        check="pycode:" + (Path(self.library.root) / str(row["artifact"])).read_text(encoding="utf-8"),
                        covers="a check this class left behind on a previous run; "
                               "its blind spots are whatever they were then",
                        author="agent", about="")
                    out.trace.append("reused a check from the library: %s" % row["artifact"])
                except RegisterViolation:
                    pass

        # Criteria come from whoever is eligible, before anyone is chosen to do
        # the work. Registering them first is the whole point: a check proposed
        # after the executor is picked is a check picked to suit it.
        seen: set = set()
        for ex in self.executors:
            for name, check, covers in ex.propose_criteria(contract, ws):
                if name in seen:
                    continue
                seen.add(name)
                try:
                    register.register(name=name, check=check, covers=covers,
                                      author="agent")
                except RegisterViolation as e:
                    out.trace.append("criterion refused: %s" % e)

        if not register.criteria():
            e = cheapest_question(ambiguous=(
                "nothing here says what a correct result looks like, and I "
                "cannot derive a check from the statement. What would count as "
                "done?"))
            out.escalations.append(e)
            answer = self.human(e) if self.human else None
            if answer:
                register.register(name="human:done", check=answer,
                                  covers="supplied by the person delegating",
                                  author="human")
            else:
                out.refused = ("no acceptance criterion exists and none could be "
                               "derived; proceeding would produce an assertion, "
                               "not a completed task")
                out.seconds = time.time() - t0
                return out

        register.seal()
        out.trace.append("register sealed at %s with %d criteria (sigma=%.2f)"
                         % (register.head[:12], len(register.criteria()), register.sigma()))

        # 4. Reversibility, before the first mutation rather than after it.
        ledger = UndoLedger(ws, store / "snapshots")
        rev = (Reversibility.FREE if contract.reversibility.value >= 3 else
               Reversibility.CHEAP if contract.reversibility.value == 2 else
               Reversibility.COSTLY if contract.reversibility.value == 1 else
               Reversibility.NONE)
        step = Step(what="the work itself", reversibility=rev)
        allowed, why = ledger.gate(step)
        if not allowed:
            e = cheapest_question(needs_permission=why)
            out.escalations.append(e)
            answer = self.human(e) if self.human else None
            if not answer:
                out.refused = why
                out.seconds = time.time() - t0
                return out
            ledger.gate(step, authorisation=str(answer))
        base = step.snapshot
        out.trace.append("snapshot %s taken before any change" % base)

        # 5. Choose who does it, attempt, accept; on failure classify and
        #    re-route rather than run the same thing again and hope.
        feedback: List[str] = []
        ck = class_key or task_id.split("#")[0]
        tried: List[str] = []
        per_executor: Dict[str, int] = {}

        choice = self.router.choose(contract, ck)
        for name, why in choice.excluded:
            out.trace.append("excluded %s: %s" % (name, why))
        if choice.executor is None:
            e = cheapest_question(stuck_on=choice.because)
            out.escalations.append(e)
            out.refused = choice.because
            out.seconds = time.time() - t0
            return out
        out.trace.append("routed to %s (%s)" % (choice.executor.name, choice.because))

        for attempt in range(1, self.max_attempts + 1):
            out.attempts = attempt
            ex = choice.executor
            if ex is None:
                break
            per_executor[ex.name] = per_executor.get(ex.name, 0) + 1
            result = ex.execute(contract, ws, feedback)
            confidence = float(result.confidence)

            ask, why = rather_ask_than_guess(confidence, contract.p_star, contract.rho)
            if ask:
                e = cheapest_question(stuck_on=why)
                out.escalations.append(e)
                answer = self.human(e) if self.human else None
                if not answer:
                    out.refused = why
                    break
                feedback.append(str(answer))

            acc = accept(register, ws)
            out.acceptance = acc
            # The competence model learns from the verdict, never from the
            # executor's account of how it went.
            self.competence.observe(ex.name, ck, acc.accepted)
            out.trace.append("attempt %d by %s: %s" % (attempt, ex.name,
                                                       "accepted" if acc.accepted
                                                       else "not accepted"))
            if acc.accepted:
                out.accepted = True
                break

            kind = classify_failure(acc, feedback, per_executor[ex.name])
            out.route.append((ex.name, kind.value))
            failed = [n for n, ok, _ in acc.results if not ok]
            feedback.append("these registered checks failed: %s" % ", ".join(failed))
            out.trace.append("failure classified %s after %s"
                             % (kind.value, ex.name))

            if attempt >= self.max_attempts:
                break
            if base:
                ledger.restore(base)
                out.trace.append("restored %s; the next attempt starts clean" % base)

            if not kind.retry_same:
                tried.append(ex.name)
            nxt = self.router.next_after_failure(kind, contract, ck, tried,
                                                 current=ex)
            if nxt.executor is None:
                e = cheapest_question(stuck_on=nxt.because)
                out.escalations.append(e)
                answer = self.human(e) if self.human else None
                if not answer:
                    out.refused = nxt.because
                    break
                feedback.append(str(answer))
            else:
                if nxt.executor.name != ex.name:
                    out.trace.append("re-routed to %s: %s"
                                     % (nxt.executor.name, nxt.because))
                choice = nxt

        # 6. Leave the check behind. This is the part that compounds.
        if out.accepted and self.library:
            out.compression = self.library.compress(
                class_key or task_id.split("#")[0], register.criteria())
            if out.compression:
                out.trace.append("compressed: %s" % out.compression.moves)

        out.seconds = time.time() - t0
        return out
