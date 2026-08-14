"""`GRP` — a research agent is a GROUP, and some of it has a body.

The design (`2026-08-04-ai4science-one-machine-design.md` §11b, lines 1436-1570)
redesigns a research agent as a **group**: one workspace, one task list, one
ceiling, members that talk to each other directly, and one agent as far as
anyone outside is concerned. Three kinds of member, defined by *what their acts
reach*:

    reasoning  -> a file in the workspace      undoable, trivially
    judging    -> a verdict and a check        never the thing that acts
    embodied   -> THE WORLD                    not undoable, ever

`registry.py` models the outside view — one agent, one ceiling. It has no
inside. This module is that inside, and it exists because the design's own
summary of itself (line 1565) is *"Nothing embodied is built"*.

**This module DISPLAYS; it does not enforce.**

That is deliberate and it is the whole boundary of this phase. The design's
hardest rule is line 1534:

    the group's ceiling is the LOWEST of its members', not the agent's.

Making that rule *bind* would narrow what every research agent may do — an
authority change, and the owner's to make, not this module's. So `ceiling()`
below computes the number and the board prints it beside the registry's, and
**nothing reads it to decide anything**. Where the two disagree, that gap is
the finding, shown rather than silently closed.

A test asserts this module cannot enforce: no `decide`, `allow`, `permit`,
`enforce` or `cap` function exists here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

#: The three kinds, in the order the design introduces them (lines 1452-1456).
#: The order is not cosmetic: it runs from "reaches a file" to "reaches the
#: world", which is the axis the whole section is organised on.
KINDS = ("reasoning", "judging", "embodied")

#: Ceilings, most restrictive first. `min()` over this ordering is the design's
#: "lowest of its members'". A0 is the most restrictive, A3 the least.
CEILING_ORDER = ("A0", "A1", "A2", "A3")


def _rank(ceiling: str) -> int:
    try:
        return CEILING_ORDER.index(ceiling.upper())
    except ValueError:
        # An unknown ceiling is treated as the MOST restrictive, never the
        # least. A group whose ceiling was widened by a typo would be the
        # back door line 1536 names.
        return 0


@dataclass(frozen=True)
class Member:
    """One member of a group. `kind` decides what its acts can reach."""
    name: str
    kind: str
    acts_on: str
    #: Every member's refusal, per the design's table (lines 1543-1549). A
    #: member whose refusal cannot be stated is one nobody can predict.
    refusal: str
    ceiling: str
    #: Whether this member exists as running software. The design says the
    #: reasoning and judging members are built or specified, and that
    #: **nothing embodied is built** (line 1565). A page that did not carry
    #: this would read as though the bench were wired up.
    built: bool = True

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.kind!r} is not one of {KINDS}")

    @property
    def irreversible(self) -> bool:
        """An embodied act is irreversible, and treated so by default (1521).

        Not a property of the particular act — of the kind. `undo`'s sentence
        (*this will not pretend it did*) is the normal case for a body, not
        the edge case.
        """
        return self.kind == "embodied"

    @property
    def may_verify_own_act(self) -> bool:
        """Never, for a body (lines 1529-1533).

        The group's verifier judges from evidence the body produced, not from
        the body's report of what it did.
        """
        return not self.irreversible


@dataclass(frozen=True)
class Group:
    """One research agent, from the inside. One workspace, one task list."""
    agent_id: str
    members: List[Member] = field(default_factory=list)

    @property
    def ceiling(self) -> str:
        """The design's rule, line 1534: the LOWEST of its members'.

        Computed, never enforced — see the module docstring.
        """
        if not self.members:
            return CEILING_ORDER[0]
        return min((m.ceiling for m in self.members), key=_rank)

    @property
    def embodied(self) -> List[Member]:
        return [m for m in self.members if m.kind == "embodied"]

    @property
    def has_unbuilt(self) -> bool:
        return any(not m.built for m in self.members)

    def by_kind(self, kind: str) -> List[Member]:
        return [m for m in self.members if m.kind == kind]

    def gap_against(self, agent: Agent) -> Optional[str]:
        """Where the registry's ceiling and the group's disagree.

        `None` when they agree. This is the sentence the design predicts at
        line 1536 — *"released to A2 by the back door"* — and printing it is
        the entire point of computing a group ceiling nothing enforces yet.
        """
        if _rank(self.ceiling) == _rank(agent.ceiling):
            return None
        return (f"the registry releases {agent.id} to {agent.ceiling}; its "
                f"members' lowest is {self.ceiling}. Nothing enforces the "
                f"lower one yet, so the group acts at {agent.ceiling} today.")


#: The one worked example the design gives, lines 1541-1552 — computational
#: imaging, "because it is the one with real optics". Every row below is that
#: table; the ceilings are the design's reasoning about each kind, not taste:
#:
#:   * reasoning and judging members act on files, verdicts and checks — all
#:     re-runnable, so the everyday A2 (`registry.EVERYDAY_CEILING`).
#:   * the bench is A1 because line 1521 says an embodied act "needs the grant
#:     that irreversible acts need, EVERY time, and a standing grant does not
#:     cover it" — which is A1, where consequential acts stop at the owner.
#:
#: So the group's lowest is A1 while the registry releases the agent to A2.
#: That gap is the design's own prediction, and the board prints it.
GROUPS: Dict[str, List[Member]] = {
    "computational-imaging": [
        Member("planner", "reasoning", "plan0.md",
               "refuses a criterion no independent verifier can read", "A2"),
        Member("reconstruction runner", "reasoning", "the GPU, files",
               "refuses when the corpus is absent, naming the fetch command",
               "A2"),
        Member("domain verifier", "judging", "the benchmark",
               "refuses to judge a plan that has drifted from what was released",
               "A2"),
        Member("teacher", "judging", "the owner's own check",
               "refuses to report a pass it cannot hand the owner a way to re-run",
               "A2"),
        Member("optical bench", "embodied", "mask, stage, camera",
               "refuses every act without a grant naming that act; reports "
               "what it moved, never what it intended",
               "A1", built=False),
    ],
}


def of(config: Config, agent_id: str) -> Optional[Group]:
    """The group behind one agent id, or `None` if that agent is not a group.

    Most agents are not. `social` and `funding` have no bench and no domain
    verifier, and inventing members for them would make the page a diagram
    instead of a record.
    """
    members = GROUPS.get(agent_id)
    if members is None:
        return None
    return Group(agent_id=agent_id, members=list(members))


def all_of(config: Config) -> List[Group]:
    """Every agent in this registry that is modelled as a group."""
    out = []
    for agent in config.workers():
        got = of(config, agent.id)
        if got is not None:
            out.append(got)
    return out
