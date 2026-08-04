"""What a research agent may pursue, and what it may never touch.

An autonomous research agent optimises. Given a benchmark and a night, it will
find the shortest path to a better number — not from malice, but because that is
what optimisation is. The shortest path is almost always to change what "better"
means: edit the split, soften the metric, re-run the judge.

So the three things that define "better" are named here as **never touched**, and
they are named in the constructor rather than left to a prompt:

    benchmark   the data, the split, the held-out set
    metric      what counts as an improvement
    verifier    what counts as passed

A charter cannot be built without them. `Charter(..., never_touch=())` raises —
there is no way to declare an agent that is allowed to score itself, because the
class refuses to represent one.

This is the machine-checkable half of a rule the imaging agent already keeps by
hand with ``_NEVER_STAGE``: the answer key never enters the sandbox. That worked
because someone remembered. Six agents is where remembering stops working.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple

#: The three substrates no research agent may modify, ever. Extended per agent,
#: never reduced.
FORBIDDEN: Tuple[str, ...] = ("benchmark", "metric", "verifier")

#: The three it may. An agent that could improve nothing would not be a research
#: agent; the point is that the list is finite and declared.
IMPROVABLE: Tuple[str, ...] = ("method", "plan", "own_parameters")


class CharterViolation(Exception):
    """Raised when an agent asks to touch something its charter forbids.

    Carries the reason, because a refusal a caller cannot explain to the owner is
    a refusal the owner will route around."""


@dataclass(frozen=True)
class Charter:
    """One agent's field, and the boundary of its autonomy."""

    name: str
    field: str
    subfields: Tuple[str, ...]
    #: What it may improve. Must be a subset of IMPROVABLE.
    may_improve: Tuple[str, ...]
    #: Beyond FORBIDDEN — domain-specific things this agent must not touch, e.g.
    #: the forward model for imaging, the clinical constraint set for RT.
    also_never: Tuple[str, ...] = ()
    #: Flat refusals, in the agent's own words, shown to the owner and to review.
    refusals: Tuple[str, ...] = ()
    #: Neighbouring subfields whose methods should be tried here (the transfer
    #: surface). Empty is allowed and means nobody has looked.
    transfer_from: Tuple[str, ...] = ()
    #: Work it may start unasked, once the autonomous function is on.
    autonomous_work: Tuple[str, ...] = ()
    #: Acts that always require an owner grant naming them, whatever the ceiling.
    outward_only: Tuple[str, ...] = ("publish", "submit", "email", "spend")
    #: Other research agents whose fields this one also covers. A generalist
    #: names its specialists here. See `coverage.py` for what that costs it.
    includes: Tuple[str, ...] = ()
    #: The generalist this agent narrows, if any. A specialist names it here.
    specialises: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.may_improve:
            raise ValueError("%s: a charter with nothing improvable is not a "
                             "research agent" % self.name)
        unknown = set(self.may_improve) - set(IMPROVABLE)
        if unknown:
            raise ValueError("%s: may_improve has %s, which is not one of %s"
                             % (self.name, sorted(unknown), list(IMPROVABLE)))
        overlap = set(self.may_improve) & set(self.never_touch)
        if overlap:
            raise ValueError("%s: %s is both improvable and forbidden"
                             % (self.name, sorted(overlap)))

    @property
    def never_touch(self) -> Tuple[str, ...]:
        """FORBIDDEN first, always, then whatever this domain adds.

        A property rather than a field so that no construction path can produce a
        charter without the three."""
        return FORBIDDEN + tuple(s for s in self.also_never if s not in FORBIDDEN)

    # ------------------------------------------------------------------ checks

    def covers(self, subfield: str) -> bool:
        return subfield in self.subfields

    def may(self, substrate: str) -> bool:
        return substrate in self.may_improve and substrate not in self.never_touch

    def check(self, substrate: str) -> None:
        """Raise unless this agent may improve `substrate`.

        Called before a candidate is proposed, not after it is scored — a refusal
        that arrives after the run has spent the budget has refused nothing."""
        if substrate in self.never_touch:
            raise CharterViolation(
                "%s may never modify the %s. It defines what better means, and an "
                "agent that can change it has a winning move available at every "
                "step." % (self.name, substrate))
        if substrate not in self.may_improve:
            raise CharterViolation(
                "%s has no declared authority over %r — it may improve %s. An "
                "undeclared substrate is refused rather than assumed."
                % (self.name, substrate, ", ".join(self.may_improve)))

    def check_outward(self, act: str, *, granted: Iterable[str] = ()) -> None:
        """Publishing is an outward act. So is submitting, mailing, and spending.

        The grant must name the act; a grant for `publish` does not cover
        `submit`, because a preprint and a leaderboard entry are different
        decisions with different consequences."""
        if act in self.outward_only and act not in set(granted):
            raise CharterViolation(
                "%s: %r leaves the machine and needs an owner grant naming it. "
                "Granted here: %s" % (self.name, act, ", ".join(sorted(granted)) or "nothing"))

    def scored_on(self, benchmark_author: str) -> None:
        """A field agent will want to build benchmarks, because its field needs
        them. Allowed — but it may not then be scored on its own exam."""
        if benchmark_author == self.name:
            raise CharterViolation(
                "%s authored this benchmark and may not be scored on it. Propose "
                "it, hand it over, and become an entrant like anyone else."
                % self.name)

    # ------------------------------------------------------------------ render

    def describe(self) -> str:
        L = ["%s — %s" % (self.name, self.field), ""]
        L.append("subfields: " + ", ".join(self.subfields))
        L.append("may improve: " + ", ".join(self.may_improve))
        L.append("never touches: " + ", ".join(self.never_touch))
        if self.transfer_from:
            L.append("watches for transfer from: " + ", ".join(self.transfer_from))
        if self.refusals:
            L.append("")
            L += ["refuses: " + r for r in self.refusals]
        return "\n".join(L)
