"""The group's ceiling stops being descriptive here — it decides the grant.

``tests/test_research_group_ceiling.py`` pins the RULE: the group's ceiling is
the lowest of its acting members', because "the ceiling belongs to the act, and
the act with a body sets it". But a rule is only as real as the path that reads
it, and until now ``Group.capped`` was read by exactly two callers — the CLI
renderer (``commands/research.py``) and the board page (``sarsi/board.py``).
Both of them PRINT. Neither of them grants anything.

So the authority decision in ``machine/session.py`` — the one that answers
allow / ask / deny for every tool call — never consulted the group at all, and a
research agent whose members capped it at A0 could still act at A3. The group's
ceiling was a sentence on a board.

This file is where that ends. Everything below goes through ``decide_tool_call``
and ``SessionDriver`` — the grant path itself, with the real registry and a real
``Group`` — and asserts that the cap BINDS: an A0 group refuses an A3 act, the
shipped A1 group refuses a consequential command a declared A2 would allow, and
the cap never runs the other way (a group cannot RAISE a lower declared
ceiling). The control case matters as much as the rest: without a group, the
same A3 call is still allowed, so none of this can pass by simply breaking A3.
"""
from ai4science.harness.agents.machine.session import (
    SessionDriver, decide_tool_call,
)
from ai4science.harness.agents.research_agents import registry as ra
from ai4science.harness.agents.research_agents.group import Group, Kind, Member

#: An unclassifiable command: `frobnicate` heads no allowlist, so it needs A3.
A3_BASH = {"tool_name": "Bash",
           "tool_input": {"command": "frobnicate --quux /tmp/thing"}}
#: An unmapped tool — the other A3 door out of the governor.
A3_TOOL = {"tool_name": "SomeMcpTool", "tool_input": {}}


def _shipped_group() -> Group:
    """The real registry's group for `imaging` — nine members, no bodies, A1."""
    g = ra.build("imaging").group
    assert g.ceiling() == "A1", g.ceiling()
    return g


def _a0_group() -> Group:
    """The same real group with one EMBODIED member added, so it sits at A0.

    Built here rather than shipped: nothing embodied is built, and the docs'
    embodied rows are design. Adding one is how the rule is made visible."""
    robot = Member("sample handling robot", Kind.EMBODIED, "specimens",
                   "refuses to move a specimen outside its consented scope")
    shipped = _shipped_group()
    g = Group(shipped.field, shipped.members + (robot,))
    assert g.ceiling() == "A0", g.ceiling()
    return g


def test_an_A0_group_refuses_an_A3_command():
    """Assertion 1. Declared A3, capped to A0 by a body — the command stops.

    This is the whole point: the ceiling that decides is the group's, not the
    one the agent was handed."""
    v = decide_tool_call(A3_BASH, ceiling="A3", group=_a0_group())
    assert v["decision"] != "allow", v


def test_the_driver_carries_the_cap_too():
    """Assertion 2. Not just the function — the object a live session drives.

    A cap that holds in `decide_tool_call` and leaks in `SessionDriver` is no
    cap, because the driver is what a session actually calls."""
    d = SessionDriver(ceiling="A3", group=_a0_group())
    v = d.drive(A3_BASH)
    assert v["decision"] != "allow", v
    assert d.log and d.log[-1]["verdict"] is v


def test_an_A0_group_refuses_an_unmapped_tool():
    """Assertion 3. The other A3 door. An unmapped tool is allowed only at A3,
    so an agent capped below it must not get through here either."""
    assert decide_tool_call(A3_TOOL, ceiling="A3",
                            group=_a0_group())["decision"] != "allow"
    d = SessionDriver(ceiling="A3", group=_a0_group())
    assert d.drive(A3_TOOL)["decision"] != "allow"


def test_control_without_a_group_A3_still_allows_both():
    """Assertion 4. The control, and it is load-bearing.

    Every refusal above would also hold if A3 had simply been broken. With no
    group the same two calls are allowed at A3, so what the tests above measure
    is the cap and nothing else."""
    assert decide_tool_call(A3_BASH, ceiling="A3")["decision"] == "allow"
    assert decide_tool_call(A3_TOOL, ceiling="A3")["decision"] == "allow"
    assert SessionDriver(ceiling="A3").drive(A3_BASH)["decision"] == "allow"


def test_the_cap_never_widens():
    """Assertion 5. A group is a ceiling, not a grant.

    The shipped group sits at A1; an agent declared A0 stays at A0. If the cap
    were a `max` — or simply the group's own ceiling — this write would become
    an allow, and the group would have handed out authority nobody granted."""
    call = {"tool_name": "Write",
            "tool_input": {"file_path": "notes.md", "content": "x"}}
    assert decide_tool_call(call, ceiling="A0")["decision"] == "ask"
    assert decide_tool_call(call, ceiling="A0",
                            group=_shipped_group())["decision"] == "ask"


def test_the_shipped_A1_group_caps_a_declared_A2():
    """Assertion 6. No body needed — the group as it actually ships bites.

    `git push` is consequential: allowed from A2 up, asked below. A declared A2
    agent whose group tops out at A1 has to ask, which is the improvement the
    rule was written to make, now made on the path that decides."""
    push = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    assert decide_tool_call(push, ceiling="A2")["decision"] == "allow"
    assert decide_tool_call(push, ceiling="A2",
                            group=_shipped_group())["decision"] == "ask"


def test_effective_ceiling_says_what_is_actually_in_force():
    """Assertion 7. A session can be asked what it runs at, and answers honestly.

    The declared ceiling is what was requested; `effective_ceiling` is what is in
    force — the same distinction `trust.effective_ceiling` draws when it lowers
    an unearned A3 to A2."""
    assert SessionDriver(ceiling="A3", group=_a0_group()).effective_ceiling() == "A0"
    assert SessionDriver(ceiling="A3").effective_ceiling() == "A3"
    assert SessionDriver(ceiling="A2",
                         group=_shipped_group()).effective_ceiling() == "A1"
    # and it does not widen: below the group, the declared ceiling stands
    assert SessionDriver(ceiling="A0",
                         group=_shipped_group()).effective_ceiling() == "A0"
