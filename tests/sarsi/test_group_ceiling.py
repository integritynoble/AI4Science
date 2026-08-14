"""The group's ceiling is the lowest of its members' — and it BINDS.

One-machine design §11b, line 1534. p3 computed this number and printed it; the
owner approved wiring it on 2026-08-14, so it now decides. These tests exist
because the previous docstring claimed a guard test that had never been written.

The property under test is a direction, not a value: `capped` may narrow and may
never widen. A group is data, and data can be malformed — a group that raises,
answers outside the ceiling order, or answers upward must not buy authority.
"""
import pytest

from ai4science.harness.agents.machine.session import decide_tool_call
from ai4science.harness.agents.machine.trust import capped
from ai4science.harness.agents.sarsi import group as G


def _group(*ceilings):
    return G.Group(agent_id="t", members=[
        G.Member(f"m{i}", "reasoning", "a file", "refuses nothing", c)
        for i, c in enumerate(ceilings)])


# ── the rule itself ──────────────────────────────────────────────────

def test_group_ceiling_is_the_lowest_of_its_members():
    assert _group("A2", "A2", "A1").ceiling == "A1"
    assert _group("A3", "A0").ceiling == "A0"


def test_a_lower_group_narrows_the_declared_ceiling():
    assert capped("A2", _group("A2", "A1")) == "A1"


def test_an_embodied_member_drags_the_whole_group_down():
    """The owner's own phrasing: one embodied member caps the rest."""
    g = G.Group(agent_id="imaging", members=[
        G.Member("planner", "reasoning", "plan0.md", "refuses", "A3"),
        G.Member("bench", "embodied", "mask, stage, camera",
                 "refuses every act without a grant naming it", "A0", built=False)])
    assert g.ceiling == "A0"
    assert capped("A3", g) == "A0"


# ── the direction: narrow, never widen ───────────────────────────────

def test_no_group_is_unaffected():
    """The control. A blanket tightening is a different decision."""
    assert capped("A2", None) == "A2"


def test_an_upward_answering_group_does_not_widen():
    assert capped("A1", _group("A3")) == "A1"
    assert capped("A0", _group("A3", "A2")) == "A0"


def test_a_group_that_raises_falls_back_to_the_declared_ceiling():
    class Raises:
        @property
        def ceiling(self):
            raise RuntimeError("malformed group")
    assert capped("A2", Raises()) == "A2"


@pytest.mark.parametrize("bogus", ["Z9", "", "a2 ", "A9", None, 3])
def test_a_ceiling_outside_the_order_falls_back(bogus):
    class Outside:
        ceiling = bogus
    assert capped("A2", Outside()) == "A2"


def test_an_empty_group_does_not_widen():
    """`Group.ceiling` returns the most restrictive value for no members, so
    this narrows — the one thing it must never do is widen."""
    assert capped("A2", G.Group(agent_id="empty", members=[])) == "A0"


# ── it lands before the level is read ────────────────────────────────

def test_the_cap_binds_a_real_decision_at_the_chokepoint():
    """A2 allows a consequential command; the same call under a group whose
    lowest member is A1 must not."""
    call = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    assert decide_tool_call(dict(call), ceiling="A2")["decision"] == "allow"
    got = decide_tool_call(dict(call), ceiling="A2", group=_group("A2", "A1"))
    assert got["decision"] == "ask"


def test_the_cap_does_not_blanket_deny():
    """Read-only work is unaffected — narrowing is not breakage."""
    call = {"tool_name": "Read", "tool_input": {"file_path": "README.md"}}
    assert decide_tool_call(call, ceiling="A2",
                            group=_group("A1"))["decision"] == "allow"


def test_a_malformed_group_leaves_the_decision_as_declared():
    class Raises:
        @property
        def ceiling(self):
            raise RuntimeError("boom")
    call = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    assert decide_tool_call(call, ceiling="A2",
                            group=Raises())["decision"] == "allow"


# ── the worked example the board shows ───────────────────────────────

def test_the_imaging_group_caps_to_a1():
    g = G.of(None, "computational-imaging")
    assert g is not None and g.ceiling == "A1"
    assert capped("A2", g) == "A1"
