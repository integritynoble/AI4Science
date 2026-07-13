from ai4science.harness.agents.pocket.agent import run_pocket
from ai4science.harness.agents.pocket.tools import Tool


def test_direct_execution_no_client_no_sandbox():
    # runs with no client, no sandbox — pure Tier-D.
    ctx = {}
    out = run_pocket(intent="jot down: pick up laundry", granted={"notes"}, ctx=ctx)
    assert out["status"] == "done"
    assert out["tool"] == "note_write"
    assert ctx["notes"] == ["jot down: pick up laundry"]


def test_permission_gate_refuses_and_never_calls_fn():
    called = []

    def boom(intent, ctx):
        called.append(intent)
        raise AssertionError("fn must not run when permission ungranted")

    reg = (Tool("note_write", "notes", "reversible_write", boom, match=("note",)),)
    out = run_pocket(intent="note this", registry=reg, granted=set())
    assert out["status"] == "refused"
    assert "notes" in out["reason"]
    assert called == []


def test_risk_ceiling_hands_off_before_any_tool():
    # a consequential intent must route out even if a tool would keyword-match.
    def boom(intent, ctx):
        raise AssertionError("no tool should run for a consequential intent")

    reg = (Tool("payer", "notes", "reversible_write", boom, match=("pay",)),)
    out = run_pocket(intent="pay Bob $20", registry=reg, granted={"notes"})
    assert out["status"] == "handoff"
    assert out["target"] == "host"
    assert out["kind"] == "spend"


def test_advisory_fallback_when_no_tool_matches():
    out = run_pocket(intent="explain quantum tunnelling to me", granted={"notes"})
    assert out["status"] == "advised"
    assert out["answer"] == "advisory: explain quantum tunnelling to me"


def test_injected_select_and_advise_are_honored():
    hits = []
    tool = Tool("t", "", "read", lambda i, c: {"ok": i}, match=())

    def select(intent, registry):
        hits.append(intent)
        return tool

    out = run_pocket(intent="anything", registry=(tool,), select=select)
    assert out == {"status": "done", "tool": "t", "side_effect": "read", "result": {"ok": "anything"}}
    assert hits == ["anything"]

    out2 = run_pocket(intent="no match here", registry=(), advise=lambda i: f"LLM says: {i}")
    assert out2 == {"status": "advised", "answer": "LLM says: no match here"}


def test_no_permission_tool_runs_without_grant():
    # capability_status has no permission — runs even with empty grant set.
    out = run_pocket(intent="show my progress", granted=set(),
                     ctx={"capabilities": {"chem": 0.5}})
    assert out["status"] == "done"
    assert out["tool"] == "capability_status"
    assert out["result"] == {"capabilities": {"chem": 0.5}}
