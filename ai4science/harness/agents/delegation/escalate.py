"""Asking for the least help that unblocks, and preferring to ask over to guess.

Two results drive this.

**Depth matters more than count.** Ten factual clarifications and one message
saying "use algorithm X" are one and ten by count and the wrong way round by
cognition. So the harness picks the *shallowest* question that would unblock it,
and records the depth it reached.

**A correct escalation dominates a confident failure** on any class where being
wrong costs anything. An escalation has no loss term: the task is not done, and
the damage is not done either. It costs human load, which is a different budget.
So when confidence is below what the class requires, asking is not a weakness of
the agent -- it is the arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

#: Critical Intervention Depth. The number is the claim being made about how
#: much of the thinking the human did.
DEPTH: Dict[int, str] = {
    0: "governance or permission only",
    1: "a fact the evidence did not contain",
    2: "correction of one wrong action",
    3: "strategy for a subproblem",
    4: "strategy for the whole task",
    5: "the core insight",
    6: "the problem itself",
}


@dataclass
class Escalation:
    """One question, at the depth it actually reaches."""

    question: str
    cid: int
    because: str
    blocking: bool = True

    def __post_init__(self) -> None:
        if self.cid not in DEPTH:
            raise ValueError("cid must be 0..6")

    def as_note(self) -> str:
        return "[CID%d %s] %s -- %s" % (self.cid, DEPTH[self.cid], self.question,
                                        self.because)


def cheapest_question(missing_fact: Optional[str] = None,
                      needs_permission: Optional[str] = None,
                      ambiguous: Optional[str] = None,
                      stuck_on: Optional[str] = None) -> Optional[Escalation]:
    """The shallowest escalation that fits the situation.

    Ordered on purpose. A permission is CID0 and costs the level nothing; a fact
    is CID1; an ambiguity in the stated outcome is CID2; being stuck is CID3 and
    is the first one that admits the agent could not do the thinking. An agent
    that reaches for the last of these when the first would do has thrown away
    two levels for no reason.
    """
    if needs_permission:
        return Escalation(needs_permission, 0,
                          "authorisation, not cognition: the action is already chosen")
    if missing_fact:
        return Escalation(missing_fact, 1,
                          "the evidence available does not contain it")
    if ambiguous:
        return Escalation(ambiguous, 2,
                          "the stated outcome admits more than one reading")
    if stuck_on:
        return Escalation(stuck_on, 3,
                          "a subproblem strategy is genuinely missing")
    return None


def rather_ask_than_guess(confidence: float, p_star: float, rho: float) -> Tuple[bool, str]:
    """Is escalating better than attempting, on the arithmetic?

    Attempting has expected value ``c*V - (1-c)*rho*V``. Escalating scores no
    value and incurs no loss. So attempt only while the first is positive, which
    is exactly ``confidence >= p_star``.
    """
    if confidence >= p_star:
        return False, ""
    lost = (1 - confidence) * rho - confidence
    return True, ("attempting at confidence %.2f on a class needing %.3f has "
                  "negative expected value (%.2f per unit of success value); an "
                  "escalation costs human time instead of the loss"
                  % (confidence, p_star, lost))
