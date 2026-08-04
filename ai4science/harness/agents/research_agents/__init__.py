"""The governor's six research agents, and what bounds them.

    charter      the field, what may be improved, and the three things that may
                 never be — benchmark, metric, verifier
    selfmodel    dimensions with the measurement behind each; unmeasured stays
                 unmeasured, and the limits line cannot be omitted
    budget       what a night costs, and a stop that does not ask for more
    fieldmap     what the field claims and which claims nobody has checked
    improvement  the six checks a candidate survives before it is an improvement
    registry     the six, built

**These are market listings, not private agents.** They are authored by the
governor, accepted like any other listing, and anyone may find them in
agents-search and install them. There is no visibility gate here on purpose: the
thing that makes them the governor's is that the governor wrote them, not that
anyone else is kept out.

What *is* enforced is what any research agent may do once installed — the
charter, the budget and the off-by-default switch below. Those bound the agent's
own autonomy, which is a different question from who may run it.

The domain content matches the design set in ``docs/research-agents/``.
"""
from __future__ import annotations

from .budget import Budget, BudgetExhausted, Switch
from .charter import Charter, CharterViolation, FORBIDDEN, IMPROVABLE
from .fieldmap import Claim, FieldMap
from .improvement import Improvement, SeedResult, no_change
from .registry import NAMES, ResearchAgent, build, build_all
from .selfmodel import Dimension, SelfModel, Unobserved

__all__ = [
    "Budget", "BudgetExhausted", "Switch",
    "Charter", "CharterViolation", "FORBIDDEN", "IMPROVABLE",
    "Claim", "FieldMap",
    "Improvement", "SeedResult", "no_change",
    "NAMES", "ResearchAgent", "build", "build_all",
    "Dimension", "SelfModel", "Unobserved",
]
