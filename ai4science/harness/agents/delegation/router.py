"""Choosing who does the work, and what to do when they fail.

The score is the one the delegation objective implies:

    Score(a, q) = P(verified success | a, q) * value  -  cost  -  risk

with ``P`` taken pessimistically, from verified outcomes only. Two rules keep
it honest:

**An executor whose lower bound cannot reach the class's p\\* is not a
candidate.** Not "less preferred" -- not eligible. A class needing 0.97 is not
served by an executor verified at 0.6 however cheap it is.

**A failure re-routes by kind.** Specification failures go back to the contract,
capability failures go to a different executor, and only execution and
environment failures justify the same one again. This is the difference between
retrying and hoping.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .contract import Contract
from .executor import CompetenceModel, Executor, FailureKind


@dataclass
class Choice:
    executor: Optional[Executor]
    score: float
    because: str
    eligible: Tuple[str, ...] = ()
    excluded: Tuple[Tuple[str, str], ...] = ()


class Router:
    #: Observations before a lower bound may bench an executor.
    MIN_EVIDENCE_TO_EXCLUDE = 8

    def __init__(self, executors: Sequence[Executor], competence: CompetenceModel,
                 risk_weight: float = 1.0, cost_weight: float = 0.05) -> None:
        self.executors = list(executors)
        self.competence = competence
        self.risk_weight = risk_weight
        self.cost_weight = cost_weight

    def choose(self, contract: Contract, class_key: str,
               exclude: Sequence[str] = ()) -> Choice:
        excluded: List[Tuple[str, str]] = []
        scored: List[Tuple[float, Executor, str]] = []

        for ex in self.executors:
            if ex.name in exclude:
                excluded.append((ex.name, "already failed on this task for a "
                                          "reason that will not change"))
                continue
            c = self.competence.get(ex.name, class_key)
            p = c.lower()
            # Unproven executors are not assumed bad; they are assumed unknown,
            # and an unknown may be tried where the class tolerates being wrong.
            #
            # The evidence bar is deliberately high. Benching an executor on
            # three observations is the heroic-run error run backwards: a lower
            # bound that noisy will exclude a competent executor after an
            # unlucky start, and an excluded executor never gets the evidence
            # that would readmit it. An earlier version used three and refused
            # tasks nothing was wrong with.
            if c.evidence >= self.MIN_EVIDENCE_TO_EXCLUDE and p < contract.p_star:
                excluded.append((ex.name, "verified at %.2f on this class, below "
                                          "the %.2f it requires" % (p, contract.p_star)))
                continue
            cost = float(ex.capabilities().get("cost", 1.0))
            risk = (1.0 - p) * contract.rho
            score = p * contract.value - self.cost_weight * cost - self.risk_weight * risk
            scored.append((score, ex, "P>=%.2f on %.0f observations, cost %.1f"
                           % (p, c.evidence, cost)))

        if not scored:
            return Choice(None, float("-inf"),
                          "no executor is eligible for this class at the "
                          "reliability it requires", (), tuple(excluded))
        scored.sort(key=lambda t: -t[0])
        best_score, best, why = scored[0]
        return Choice(best, best_score, why,
                      tuple(e.name for _, e, _ in scored), tuple(excluded))

    def next_after_failure(self, kind: FailureKind, contract: Contract,
                           class_key: str, tried: Sequence[str],
                           current: Optional[Executor] = None) -> Choice:
        """Where a failure of this kind should go next.

        ``current`` is the executor that just failed, and for the kinds that
        mean "try again" it is returned unchanged. An earlier version re-scored
        instead, which silently swapped executors on every failure -- so each
        one kept restarting from its first attempt, none ever got a second, and
        a budget of four attempts bought four first attempts.
        """
        if kind is FailureKind.SPECIFICATION:
            return Choice(None, 0.0, "the contract is at fault, not the executor; "
                                     "re-specifying is the next move, not re-running")
        if kind is FailureKind.VERIFICATION:
            return Choice(None, 0.0, "the check could not decide; a stronger "
                                     "independent verifier is needed before any "
                                     "more work")
        if kind.retry_same and current is not None:
            return Choice(current, 0.0,
                          "same executor again: the failure was a slip, and it "
                          "now knows which checks it failed")
        # CAPABILITY: this executor is wrong for this class. Someone else, or
        # nobody.
        return self.choose(contract, class_key, exclude=tried)
