"""Appendix B sub-project 3b (Task 2): run_imaging_task binds to a foundry
agent_id -> the run's DERIVED ceiling (from the CP) drives the contract, not
the caller-passed capability_profile. The no-agent_id path is unchanged."""
from ai4science.harness.agents.imaging import agent as agent_mod


class _FakeClient:
    def __init__(self, derived_profile):
        self._derived = derived_profile
        self.open_run_calls = []
        self.staged = []
    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1", agent_id=None):
        self.open_run_calls.append({"capability_profile": capability_profile,
                                    "interaction_profile": interaction_profile, "agent_id": agent_id})
        return {"run_id": "R", "workspace_path": "/tmp/does-not-matter",
                "capability_profile": self._derived}
    def stage_input(self, run_id, rel, data): self.staged.append(rel)
    def get_last_known_good(self, kind, name): return None


def test_agent_id_binds_run_and_contract_uses_derived_profile(tmp_path, monkeypatch):
    captured = {}
    def _stub_run_task(*, run_id, contract, client, planner, verifier, store, task_id, on_ask=None):
        captured["contract"] = contract
        captured["run_id"] = run_id
        return {"status": "stubbed"}
    # stub the PEV loop and stage-loop's filesystem walk so this stays a unit test
    monkeypatch.setattr(agent_mod, "run_task", _stub_run_task)
    monkeypatch.setattr(agent_mod, "seed_cassi_workspace", lambda ws, seed=42: {})
    monkeypatch.setattr(agent_mod.Path, "rglob", lambda self, pat: iter(()))

    client = _FakeClient(derived_profile="A2")     # CP derives A2 for this agent
    out = agent_mod.run_imaging_task(workspace=tmp_path / "ws", client=client,
                                     store=object(), task_id="t1",
                                     agent_id="agent-A", capability_profile="A0",  # caller asks A0
                                     governed=False)
    assert out["status"] == "stubbed"
    assert client.open_run_calls[0]["agent_id"] == "agent-A"
    assert captured["contract"].capability_profile == "A2"   # DERIVED, not the A0 the caller passed


def test_no_agent_id_is_unbound_and_unchanged(tmp_path, monkeypatch):
    def _stub_run_task(*, run_id, contract, client, planner, verifier, store, task_id, on_ask=None):
        captured_contract.append(contract); return {"status": "stubbed"}
    captured_contract = []
    monkeypatch.setattr(agent_mod, "run_task", _stub_run_task)
    monkeypatch.setattr(agent_mod, "seed_cassi_workspace", lambda ws, seed=42: {})
    monkeypatch.setattr(agent_mod.Path, "rglob", lambda self, pat: iter(()))

    client = _FakeClient(derived_profile="A2")
    agent_mod.run_imaging_task(workspace=tmp_path / "ws", client=client, store=object(),
                               task_id="t2", capability_profile="A1", governed=False)
    assert client.open_run_calls[0]["agent_id"] is None       # unbound
    assert captured_contract[0].capability_profile == "A1"     # caller profile used, as before


def test_foundry_agent_fails_closed_on_dead_socket(tmp_path):
    from ai4science.harness.control_plane.client import ControlPlaneClient
    c = ControlPlaneClient(str(tmp_path / "nonexistent.sock"), timeout=0.5)
    assert c.foundry_agent("agent-A") == {}
