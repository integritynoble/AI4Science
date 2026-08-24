"""The written policy a human evaluator follows at each intervention budget.

A benchmark that says "run it at H1" and leaves the evaluator to judge what H1
permits is not measuring the same thing twice. This module is that policy,
written down, so two evaluators reach the same verdict and a third can audit
what was allowed.

The distinction the whole scale turns on:

    "Yes, you may publish that."            -- governance. Does not count.
    "Your approach is wrong; use Bayesian
     optimization instead."                 -- cognition. Counts, at CID4.

Governance is logged and reported separately. A system operating under strict
approval requirements is not thereby less intelligent, and a benchmark that
scores it as though it were is measuring its deployment policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .spec import BUDGETS, CID_MEANING, budget_index


@dataclass(frozen=True)
class BudgetPolicy:
    """What a human may and may not do at one budget."""

    budget: str
    summary: str
    permitted: Tuple[str, ...]
    forbidden: Tuple[str, ...]
    #: The deepest CID a human may reach without invalidating the run at this
    #: budget. An intervention above it means the episode does not count as
    #: evidence for the budget it claims.
    max_cid: int

    def allows(self, cid: int) -> bool:
        return cid <= self.max_cid


POLICY: Dict[str, BudgetPolicy] = {
    "H0": BudgetPolicy(
        budget="H0",
        summary="No human cognitive contribution after the task is stated.",
        permitted=(
            "Governance: authorise or refuse an action the agent has already chosen.",
            "Environment repair the agent could not perform and did not need to reason about "
            "(restarting a crashed service, restoring a quota).",
        ),
        forbidden=(
            "Any answer to a question about what to do next.",
            "Any hint, including 'have you checked X' and 'that does not look right'.",
            "Restating the task in more helpful terms.",
        ),
        max_cid=0,
    ),
    "H1": BudgetPolicy(
        budget="H1",
        summary="Exception-only. External facts the agent genuinely cannot obtain, and nothing else.",
        permitted=(
            "Everything H0 permits.",
            "Supplying a fact that is genuinely unavailable to the agent -- a credential, "
            "an external measurement, a decision only the principal can make. It must be "
            "listed in the task's permitted_information, or it is not an H1 answer.",
        ),
        forbidden=(
            "Strategy of any kind, for the task or for any subproblem.",
            "Diagnosis. Naming the cause of a failure is CID3 or higher even when it is one word.",
            "Confirming or denying that an approach is promising.",
        ),
        max_cid=1,
    ),
    "H2": BudgetPolicy(
        budget="H2",
        summary="Occasional clarification, and correction of a single wrong action.",
        permitted=(
            "Everything H1 permits.",
            "Clarifying an ambiguity in the stated outcome.",
            "Correcting one action that is wrong, without supplying the right strategy.",
        ),
        forbidden=(
            "Supplying the task strategy or a subproblem strategy.",
            "Repeated correction that amounts to steering step by step.",
        ),
        max_cid=2,
    ),
    "H3": BudgetPolicy(
        budget="H3",
        summary="Periodic review. The human may set direction at checkpoints.",
        permitted=(
            "Everything H2 permits.",
            "At a declared checkpoint, telling the agent which subproblem to attack next.",
        ),
        forbidden=(
            "Supplying the overall task strategy.",
            "Intervening between checkpoints other than as H2 permits.",
        ),
        max_cid=3,
    ),
    "H4": BudgetPolicy(
        budget="H4",
        summary="Frequent guidance. The human's planning repeatedly determines the next step.",
        permitted=("Everything H3 permits.", "Choosing the overall approach."),
        forbidden=("Performing the work.",),
        max_cid=4,
    ),
    "H5": BudgetPolicy(
        budget="H5",
        summary="Step by step. The human supplies the procedure.",
        permitted=("Everything H4 permits.", "Naming each operation in order."),
        forbidden=("Nothing, short of the human doing the task themselves.",),
        max_cid=5,
    ),
}


def classify(kind: str, cid: int) -> bool:
    """Is this intervention cognitive assistance?

    The single rule: CID0 is governance, everything above it is cognition.
    Kind is recorded for the report but does not decide -- an "approval" that
    also told the agent what to do is a rescue wearing a signature.
    """
    return cid > 0


def violation(budget: str, cid: int) -> str:
    """Empty if this intervention is within policy, else why it is not."""
    p = POLICY[budget]
    if p.allows(cid):
        return ""
    return ("CID%d (%s) exceeds what %s permits (max CID%d). The episode is "
            "evidence for a budget no looser than the help it actually "
            "received." % (cid, CID_MEANING[cid], budget, p.max_cid))


def demoted_budget(cid: int) -> str:
    """The tightest budget an episode with this depth of help is evidence for.

    Used to relabel rather than discard: a run intended as H1 that took a CID3
    rescue is a real H3 datum, and throwing it away loses information while
    counting it as H1 inflates the level.
    """
    for h in BUDGETS:
        if POLICY[h].allows(cid):
            return h
    return BUDGETS[-1]


def written_policy() -> str:
    """The policy as a page an evaluator can be handed before a run."""
    out = ["DLI-Bench intervention policy", "=" * 29, ""]
    for h in BUDGETS:
        p = POLICY[h]
        out += ["%s -- %s" % (h, p.summary), "  permitted:"]
        out += ["    + %s" % x for x in p.permitted]
        out += ["  forbidden:"]
        out += ["    - %s" % x for x in p.forbidden]
        out += ["  max CID: %d (%s)" % (p.max_cid, CID_MEANING[p.max_cid]), ""]
    out += ["Critical Intervention Depth", "-" * 27]
    out += ["  CID%d  %s" % (k, v) for k, v in sorted(CID_MEANING.items())]
    out += ["", "Governance actions are logged and reported separately. They do",
            "not lower the delegation level, because they supply no missing",
            "cognition. Cognitive assistance does, at the depth it reached."]
    return "\n".join(out)
