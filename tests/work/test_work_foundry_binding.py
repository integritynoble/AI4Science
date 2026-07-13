"""Appendix B sub-project 3d (Task 1): run_work_task binds to a foundry
agent_id (the CP derives the ceiling), and foundry_runner dispatches the
`work` domain to it. Mirrors the imaging binding from 3b (open-before-compile)."""
from ai4science.harness.agents.work import agent as work_mod
from ai4science.harness.agents import foundry_runner as fr

DEMAND = {"objective": "fix it", "verify_commands": [["true"]], "required_artifacts": ["x.py"]}


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
    monkeypatch.setattr(work_mod, "run_task", _stub_run_task)
    client = _FakeClient(derived_profile="A1")          # CP derives A1 for this agent
    out = work_mod.run_work_task(demand=DEMAND, client=client, store=object(), task_id="t1",
                                 governed=False, planner=object(),
                                 agent_id="W", capability_profile="A0")   # caller asks A0
    assert out["status"] == "stubbed"
    assert client.open_run_calls[0]["agent_id"] == "W"
    assert captured["contract"].capability_profile == "A1"   # DERIVED, not the A0 the caller passed


def test_no_agent_id_is_unbound_and_unchanged(monkeypatch):
    captured = {}
    def _stub_run_task(*, run_id, contract, client, planner, verifier, store, task_id, on_ask=None):
        captured["contract"] = contract; return {"status": "stubbed"}
    monkeypatch.setattr(work_mod, "run_task", _stub_run_task)
    client = _FakeClient(derived_profile="A2")          # would-be derived, must be IGNORED when unbound
    work_mod.run_work_task(demand=DEMAND, client=client, store=object(), task_id="t2",
                           governed=False, planner=object(), capability_profile="A1")
    assert client.open_run_calls[0]["agent_id"] is None
    assert captured["contract"].capability_profile == "A1"   # caller profile used, as before


def test_foundry_runner_dispatches_work_bound(monkeypatch):
    calls = []
    def _spy(*, client, store, agent_id, task_id, **kw):
        calls.append({"agent_id": agent_id, "kw": kw}); return {"status": "delivered"}
    monkeypatch.setitem(fr.DOMAIN_SPECS, "work", fr.DomainEntry(min_profile="A1", run=_spy))
    class _Rec:
        def foundry_agent(self, aid): return {"activation_state": "active", "ceiling": "A1", "domain": "work"}
    out = fr.run_foundry_agent(client=_Rec(), store=object(), agent_id="W", task_id="t",
                               demand=DEMAND)
    assert out["ok"] is True and out["ceiling"] == "A1"
    assert calls[0]["agent_id"] == "W"                       # ran bound
    assert calls[0]["kw"]["demand"] == DEMAND                # **kw carried the demand


def test_foundry_runner_refuses_work_below_a1_floor(monkeypatch):
    calls = []
    def _spy(*, client, store, agent_id, task_id, **kw):
        calls.append(agent_id); return {"status": "delivered"}
    monkeypatch.setitem(fr.DOMAIN_SPECS, "work", fr.DomainEntry(min_profile="A1", run=_spy))
    class _Rec:
        def foundry_agent(self, aid): return {"activation_state": "active", "ceiling": "A0", "domain": "work"}
    out = fr.run_foundry_agent(client=_Rec(), store=object(), agent_id="W", task_id="t", demand=DEMAND)
    assert out["ok"] is False and "ceiling" in out["reason"].lower()
    assert calls == []                                       # never dispatched
