"""Appendix B sub-project 3e (Task 1): run_research_task binds to a foundry
agent_id (the CP derives the ceiling), and foundry_runner dispatches the
`research` domain to it. Mirrors the work binding from 3d (open-before-compile)."""
from ai4science.harness.agents.research import agent as research_mod
from ai4science.harness.agents import foundry_runner as fr

DEMAND = {"question": "why?", "sources": {"a.txt": "because"},
          "coverage_points": ["because"]}


class _FakeClient:
    def __init__(self, derived_profile):
        self._derived = derived_profile
        self.open_run_calls = []
    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1", agent_id=None):
        self.open_run_calls.append({"capability_profile": capability_profile, "agent_id": agent_id})
        return {"run_id": "R", "capability_profile": self._derived}
    def stage_input(self, run_id, rel, data):
        return {"ok": True}
    def set_criteria(self, run_id, verify_commands, required_artifacts):
        return {"ok": True}


def test_agent_id_binds_run_and_contract_uses_derived_profile(monkeypatch):
    captured = {}
    def _stub_run_task(*, run_id, contract, client, planner, verifier, store, task_id, on_ask=None):
        captured["contract"] = contract; return {"status": "stubbed"}
    monkeypatch.setattr(research_mod, "run_task", _stub_run_task)
    client = _FakeClient(derived_profile="A1")          # CP derives A1 for this agent
    out = research_mod.run_research_task(demand=DEMAND, client=client, store=object(), task_id="t1",
                                         governed=False, planner=object(),
                                         agent_id="R", capability_profile="A0")   # caller asks A0
    assert out["status"] == "stubbed"
    assert client.open_run_calls[0]["agent_id"] == "R"
    assert captured["contract"].capability_profile == "A1"   # DERIVED, not the A0 the caller passed


def test_no_agent_id_is_unbound_and_unchanged(monkeypatch):
    captured = {}
    def _stub_run_task(*, run_id, contract, client, planner, verifier, store, task_id, on_ask=None):
        captured["contract"] = contract; return {"status": "stubbed"}
    monkeypatch.setattr(research_mod, "run_task", _stub_run_task)
    client = _FakeClient(derived_profile="A2")          # would-be derived, must be IGNORED when unbound
    research_mod.run_research_task(demand=DEMAND, client=client, store=object(), task_id="t2",
                                   governed=False, planner=object(), capability_profile="A1")
    assert client.open_run_calls[0]["agent_id"] is None
    assert captured["contract"].capability_profile == "A1"   # caller profile used, as before


def test_foundry_runner_dispatches_research_bound(monkeypatch):
    calls = []
    def _spy(*, client, store, agent_id, task_id, **kw):
        calls.append({"agent_id": agent_id, "kw": kw}); return {"status": "delivered"}
    monkeypatch.setitem(fr.DOMAIN_SPECS, "research", fr.DomainEntry(min_profile="A1", run=_spy))
    class _Rec:
        def foundry_agent(self, aid): return {"activation_state": "active", "ceiling": "A1", "domain": "research"}
    out = fr.run_foundry_agent(client=_Rec(), store=object(), agent_id="R", task_id="t",
                               demand=DEMAND)
    assert out["ok"] is True and out["ceiling"] == "A1"
    assert calls[0]["agent_id"] == "R"                       # ran bound
    assert calls[0]["kw"]["demand"] == DEMAND                # **kw carried the demand


def test_foundry_runner_refuses_research_below_a1_floor(monkeypatch):
    calls = []
    def _spy(*, client, store, agent_id, task_id, **kw):
        calls.append(agent_id); return {"status": "delivered"}
    monkeypatch.setitem(fr.DOMAIN_SPECS, "research", fr.DomainEntry(min_profile="A1", run=_spy))
    class _Rec:
        def foundry_agent(self, aid): return {"activation_state": "active", "ceiling": "A0", "domain": "research"}
    out = fr.run_foundry_agent(client=_Rec(), store=object(), agent_id="R", task_id="t", demand=DEMAND)
    assert out["ok"] is False and "ceiling" in out["reason"].lower()
    assert calls == []                                       # never dispatched
