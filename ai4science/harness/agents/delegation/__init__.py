"""A delegation-maximising agent harness.

The thesis this implements, and the reason it is a harness rather than a model:

    Delegation is bounded by how cheaply a mistake can be found and how cheaply
    it can be undone -- properties of the work, not of the worker. So the way to
    raise an agent's delegation frontier is to move those two properties, not to
    make the agent cleverer.

Everything here follows from that, plus one constraint:

    Acceptance cannot be delegated to the doer. Execution scales without limit;
    acceptance only transfers. A result accepted by whatever produced it is an
    assertion, not a completed task.

The harness wraps *any* solver -- a scripted policy, a local model, a
subscription CLI -- and does five things the solver does not do for itself:

1. **Reads the class before doing the work** (:mod:`.contract`). Estimates
   verifiability and reversibility, derives the reliability the class actually
   requires from its loss terms, and refuses autonomy it cannot justify.
2. **Registers a check before the work exists** (:mod:`.criterion`). Write-once,
   hash-chained, outside the solver's reach. A criterion written after the
   result is a criterion fitted to it.
3. **Makes the work reversible before doing it** (:mod:`.reversible`). Snapshot
   first; gate anything that cannot be undone.
4. **Accepts somewhere else** (:mod:`.acceptor`). A separate process, with the
   solver's write set excluded, runs the registered criteria.
5. **Escalates at the shallowest depth that unblocks** (:mod:`.escalate`), and
   prefers a correct escalation to a confident failure, because an escalation
   costs human load and a wrong answer costs the loss.

And one thing that compounds: after a class is solved, :mod:`.compress` emits
the artifact that lowers its verification cost next time. That is the only
route by which an agent legitimately raises its own frontier -- capability
improves the rate within a cell; compression moves the cell.
"""
from __future__ import annotations

from .acceptor import Acceptance, accept
from .contract import Contract, read_task
from .criterion import Criterion, CriterionRegister, RegisterViolation
from .escalate import Escalation, cheapest_question
from .loop import DelegationAgent, Outcome
from .reversible import UndoLedger, Reversibility

__all__ = [
    "Acceptance", "accept", "Contract", "read_task", "Criterion",
    "CriterionRegister", "RegisterViolation", "Escalation", "cheapest_question",
    "DelegationAgent", "Outcome", "UndoLedger", "Reversibility",
]
