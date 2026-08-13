"""A research agent is a **group**, and the group's ceiling belongs to the act.

``docs/research-agents/*.md`` says each research agent "is not one model. It is a
**group** with three kinds of member, defined by what their acts reach:
**reasoning** members touch a file, **judging** members produce a verdict and
never act, and **embodied** members touch the world and cannot be undone."
Outside the group it is one agent — one workspace, one task list, one ceiling,
one verdict. This module builds that group, and the one rule with teeth:

    **The group's ceiling is the lowest of its members', not the agent's.**
    The ceiling belongs to the act, and the act with a body sets it.

The ceiling per kind (letters from ``machine/session.py:_CEILING_ORDER``,
meanings in ``sarsi/selfaware.py:PERMITS`` — no new letters are invented here):

    REASONING  touches a file        -> A1  writes inside declared paths; a
                                            consequential command still stops
    JUDGING    never acts            -> None it produces a verdict; a member that
                                            cannot act has no authority to cap
    EMBODIED   touches the world     -> A0  needs a grant naming that act, every
                                            time; a standing night grant does not
                                            cover it (rule 1)

**JUDGING carries ``ceiling = None`` and this is the load-bearing decision.** The
doc says the ceiling belongs to the *act*, and a judging member does not act — it
produces a verdict. If judging members counted, every group would sit at A0,
because every research agent has judging members, and the rule "the lowest of its
members'" would be vacuous — always A0, regardless of what the group actually
does. So only members that *act* — reasoning and embodied — cap the group;
judging members are skipped. A future reader will want to "fix" the ``None``;
this comment is why they should not.

**Nothing embodied is populated.** The ``EMBODIED`` kind is supported by the
model so the ceiling rule is testable — add a body and the group drops to A0 —
but the pages say nothing embodied is built, so the shipped groups get the nine
reasoning-and-judging floor members and no bodies. The embodied rows in the docs
(``sample handling robot``, ``sequencing automation``) are design, not code.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional, Tuple

# Imported from the one place the ordering lives, so a change there is felt here
# rather than silently diverging.
from ..machine.session import _CEILING_ORDER


class Kind(enum.Enum):
    """What a member's acts reach — and therefore what it can cap the group to.

    The ceiling is a function of the kind and lives on the kind, so a member
    cannot be handed a ceiling that contradicts what it is."""

    #: Touches a file. Writes inside declared paths; a consequential command
    #: still stops for the owner. -> A1
    REASONING = "reasoning"
    #: Never acts — produces a verdict. A member that cannot act has no authority
    #: to cap, so it does not enter the group ceiling at all. -> None
    JUDGING = "judging"
    #: Touches the world, irreversible. Needs a grant naming that act, every
    #: time; a standing night grant does not cover it. -> A0
    EMBODIED = "embodied"


#: The ceiling each kind imposes on the group. ``None`` for JUDGING is not a
#: missing value — it is the statement that a member which never acts sets no
#: ceiling. See the module docstring.
_KIND_CEILING = {
    Kind.REASONING: "A1",
    Kind.JUDGING: None,
    Kind.EMBODIED: "A0",
}


class GroupIncomplete(Exception):
    """Raised when a group is built without a member the floor requires.

    Carries the reason, in the style of ``charter.CharterViolation``: a refusal a
    caller cannot explain to the owner is a refusal the owner will route around.
    An agent missing the verifier or the twin is not a research agent with fewer
    parts — it is *a method with a scoreboard*."""


@dataclass(frozen=True)
class Member:
    """One member of a research-agent group.

    ``ceiling`` is derived from ``kind`` and is deliberately not a field: a member
    cannot be constructed with a ceiling that contradicts its kind, because there
    is nowhere to put one."""

    name: str
    kind: Kind
    #: What its acts reach — "prior work, with citations", "the benchmark", …
    acts_on: str
    #: The one refusal that defines it, from its row in the docs' group table.
    refusal: str

    @property
    def ceiling(self) -> Optional[str]:
        """A1 for reasoning, A0 for embodied, ``None`` for judging.

        A property, not a field, so no construction path can produce a member
        whose ceiling disagrees with its kind."""
        return _KIND_CEILING[self.kind]

    def acts(self) -> bool:
        """True for members with an act that reaches past a verdict.

        Reasoning touches a file, embodied touches the world; judging produces a
        verdict and never acts. Only members that act cap the group."""
        return self.ceiling is not None


#: The nine members that exist today, as data, reusable by every field. The
#: embodied rows in the docs are NOT here — nothing embodied is built. A field
#: may add members; it may not remove any of these (see ``Group`` validation).
FLOOR: Tuple[Member, ...] = (
    # reasoning — each touches a file
    Member("literature", Kind.REASONING, "prior work, with citations",
           "refuses a claim it cannot cite, and never reads while the method is "
           "being written"),
    Member("twin", Kind.REASONING, "the cohort and site model",
           "refuses to be graded outside the regime it declares valid"),
    Member("corpus", Kind.REASONING, "the field's data source",
           "refuses when the corpus is absent, naming the fetch command rather "
           "than substituting generated data"),
    Member("method", Kind.REASONING, "the candidate solution",
           "the only member that writes the thing being judged"),
    Member("runner", Kind.REASONING, "compute",
           "refuses a run whose cost or placement it cannot state"),
    # judging — each produces a verdict and never acts
    Member("verifier", Kind.JUDGING, "the benchmark",
           "refuses to judge against a criterion written after the result"),
    Member("reproducer", Kind.JUDGING, "published artifacts alone",
           "refuses a result it cannot re-run from what was published"),
    Member("teacher", Kind.JUDGING, "the owner's own check",
           "refuses to report a score without saying what was held out"),
    Member("writer", Kind.JUDGING, "the field page and the paper",
           "writes last, from the record, never from intent"),
)

#: The two members the floor cannot do without. An agent owning both the twin
#: (what should this produce) and the verifier (did it) can pass any benchmark it
#: likes by moving one of them — so a group missing either is refused.
_REQUIRED = ("verifier", "twin")


def group_ceiling(members: Tuple[Member, ...]) -> Optional[str]:
    """The lowest ceiling among members that ACT — judging members are skipped.

    "The lowest of its members', not the agent's." With only the nine floor
    members (five reasoning at A1, four judging at None) this is A1. Add any
    embodied member and it drops to A0 — "the act with a body sets it".

    ``None`` only if no member acts, which a valid group never is."""
    acting = [m.ceiling for m in members if m.acts()]
    if not acting:
        return None
    return min(acting, key=lambda c: _CEILING_ORDER[c])


@dataclass(frozen=True)
class Group:
    """A research agent's group: a field name and its members.

    Presents outward as one agent. The floor is validated at construction — a
    group is a group of at least the nine, and always the verifier and the twin.
    """

    field: str
    members: Tuple[Member, ...] = FLOOR

    def __post_init__(self) -> None:
        have = {m.name for m in self.members}
        missing = [n for n in _REQUIRED if n not in have]
        if missing:
            raise GroupIncomplete(
                "%s: a group without its %s is not a research agent with fewer "
                "parts — it is a method with a scoreboard. The twin says what the "
                "work should produce and the verifier says whether it did; an "
                "agent owning both can pass any benchmark it likes by moving one."
                % (self.field, " or ".join(missing)))

    def acting_members(self) -> Tuple[Member, ...]:
        """Reasoning and embodied members — the ones whose acts set the ceiling.

        Judging members are excluded, because a member that never acts has no
        authority to cap the group."""
        return tuple(m for m in self.members if m.acts())

    def ceiling(self) -> Optional[str]:
        """The group's ceiling: the lowest among members that act."""
        return group_ceiling(self.members)

    def capped(self, agent_ceiling: str) -> str:
        """The agent's declared ceiling, capped by the group's.

        ``min(agent_ceiling, group_ceiling)`` by ``_CEILING_ORDER``. This is the
        improvement: an agent declared A2 whose group sits at A1 runs at A1 — the
        agent's own ceiling no longer decides. If no member acts (no valid group
        is like this), the agent's ceiling is returned unchanged."""
        gc = self.ceiling()
        if gc is None:
            return agent_ceiling
        return min((agent_ceiling, gc), key=lambda c: _CEILING_ORDER[c])

    def report(self) -> str:
        L = ["group (%s) — ceiling %s" % (self.field, self.ceiling())]
        for m in self.members:
            cap = m.ceiling if m.ceiling is not None else "—"
            L.append("  %-11s %-9s %s [%s]"
                     % (m.name, m.kind.value, m.acts_on, cap))
        return "\n".join(L)
