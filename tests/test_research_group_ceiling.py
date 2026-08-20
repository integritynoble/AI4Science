"""The group's ceiling is the lowest of its members', not the agent's.

``docs/research-agents/*.md`` says each research agent is a **group** of three
kinds of member — reasoning (touches a file), judging (produces a verdict, never
acts), embodied (touches the world, irreversible) — and that the group's ceiling
is the lowest of its members', because "the ceiling belongs to the act, and the
act with a body sets it". This file pins that rule where it has teeth.

The load-bearing decision is that **judging members carry no ceiling** and are
skipped when the group's ceiling is computed. If they counted, every group would
sit at A0 (every research agent has judging members) and the rule would be
vacuous. So the group ships at A1 — the lowest among its five reasoning members —
and an agent that declared itself A2 is capped to A1 by its group: the agent's
own ceiling no longer decides. Add a body and the group drops to A0, which is the
whole point of naming the kind even though nothing embodied is built.

The floor is nine members, and two of them — the verifier and the twin — are not
optional: an agent missing either is *a method with a scoreboard*, and the group
refuses to be one.
"""
from ai4science.harness.agents.research_agents import registry as ra
from ai4science.harness.agents.research_agents.group import (
    FLOOR, Group, GroupIncomplete, Kind, Member,
)

FLOOR_NAMES = {m.name for m in FLOOR}


def test_every_agent_has_a_group_with_the_nine_floor_members():
    """Assertion 1. Each of the seven agents carries a group; the floor is in it.

    A field may add members but may not remove any, so the check is inclusion,
    not equality — every floor member is present in every agent's group."""
    assert len(FLOOR_NAMES) == 9, sorted(FLOOR_NAMES)
    for name, agent in ra.build_all().items():
        have = {m.name for m in agent.group.members}
        assert FLOOR_NAMES <= have, (name, sorted(FLOOR_NAMES - have))


def test_group_ceiling_is_A1_as_shipped():
    """Assertion 2. No bodies, so the ceiling is the reasoning members' A1."""
    for name, agent in ra.build_all().items():
        assert agent.group.ceiling() == "A1", (name, agent.group.ceiling())


def test_the_rule_bites_an_A2_agent_is_capped_to_A1():
    """Assertion 3. The agent's own ceiling no longer decides.

    An agent that declares A2 runs at A1 because its group's acting members top
    out there — this is the improvement the rule exists to make."""
    for name, agent in ra.build_all().items():
        assert agent.group.capped("A2") == "A1", (name, agent.group.capped("A2"))
        # and it never widens: an agent below the group keeps its lower ceiling
        assert agent.group.capped("A0") == "A0", name


def test_a_body_drops_the_group_to_A0():
    """Assertion 4. The act with a body sets it.

    Built here, not added to a shipped agent — nothing embodied is built. One
    embodied member and the group's ceiling is A0, and an A2 agent is capped to
    A0."""
    robot = Member("sample handling robot", Kind.EMBODIED, "specimens",
                   "refuses to move a specimen outside its consented scope")
    g = Group("cancer", FLOOR + (robot,))
    assert g.ceiling() == "A0"
    assert g.capped("A2") == "A0"


def test_judging_members_never_cap_proved_by_construction():
    """Assertion 5. A judging member cannot lower the group, whatever it 'is'.

    If judging counted, this group — reasoning at A1 plus judging members — would
    have to reckon with them; instead the acting set is exactly the reasoning
    members and the ceiling is A1. Proved by construction: a group of one
    reasoning member and every judging member still sits at A1."""
    judges = tuple(m for m in FLOOR if m.kind is Kind.JUDGING)
    reasoning = tuple(m for m in FLOOR if m.kind is Kind.REASONING)
    assert judges and reasoning
    # verifier and twin are present, so the floor is satisfied
    g = Group("cancer", (next(m for m in reasoning if m.name == "twin"),) + judges)
    assert {m.name for m in g.acting_members()} == {"twin"}
    assert g.ceiling() == "A1"
    # and every judging member reports no ceiling at all
    assert all(m.ceiling is None for m in judges)


def test_omitting_verifier_raises():
    """Assertion 6a. A group without its verifier is refused, by name."""
    without = tuple(m for m in FLOOR if m.name != "verifier")
    try:
        Group("cancer", without)
    except GroupIncomplete as e:
        assert "verifier" in str(e)
    else:
        raise AssertionError("a group without the verifier was allowed")


def test_omitting_twin_raises():
    """Assertion 6b. A group without its twin is refused, by name. Separately."""
    without = tuple(m for m in FLOOR if m.name != "twin")
    try:
        Group("cancer", without)
    except GroupIncomplete as e:
        assert "twin" in str(e)
    else:
        raise AssertionError("a group without the twin was allowed")


def test_no_shipped_agent_has_an_embodied_member():
    """Assertion 7. Nothing embodied is built — the pages say so."""
    for name, agent in ra.build_all().items():
        bodies = [m.name for m in agent.group.members if m.kind is Kind.EMBODIED]
        assert bodies == [], (name, bodies)
