import subprocess, sys
from pathlib import Path
from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.runtime.task_store import TaskStore

class HostSimClient:
    """Stands in for the control plane: ACT/ASK by fixed decision; sandbox_execute runs
    the solver on the host workspace (simulating the container writing results/)."""
    def __init__(self, workspace, decision="ACT"):
        self.workspace = Path(workspace); self.decision = decision; self.executed = []
    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1"):
        return {"run_id": "hostsim", "capability_profile": capability_profile,
                "interaction_profile": interaction_profile, "limits": hard_limits}
    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": self.decision, "reason": "hostsim"}
    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None, workspace_target=None):
        self.executed.append(command)
        p = subprocess.run([sys.executable] + command[1:], cwd=str(self.workspace),
                           capture_output=True, text=True)
        return {"exit_code": p.returncode, "is_error": p.returncode != 0,
                "timed_out": False, "stdout": p.stdout, "stderr": p.stderr, "artifacts": []}

def test_i2_delivers_physics_verified_reconstruction(tmp_path):
    ws = tmp_path / "ws"
    client = HostSimClient(ws, decision="ACT")   # I2 → gateway would ACT the fork
    out = run_imaging_task(workspace=ws, client=client, store=TaskStore(tmp_path / "tasks"),
                           task_id="hs1", interaction_mode="I2", seed=42)
    assert out["status"] == "delivered", out
    assert client.executed and client.executed[0][1] == "code/run_solver.py"
    assert (ws / "results" / "reconstruction_xhat.npy").exists()

def test_i0_pauses_at_reconstruction_fork(tmp_path):
    ws = tmp_path / "ws"
    client = HostSimClient(ws, decision="ASK")   # I0 → gateway would ASK the fork
    asked = {}
    out = run_imaging_task(workspace=ws, client=client, store=TaskStore(tmp_path / "tasks"),
                           task_id="hs2", interaction_mode="I0", seed=42,
                           on_ask=lambda step, state: asked.setdefault("s", step.summary))
    assert out["status"] == "awaiting_owner"
    assert client.executed == []                  # never ran the reconstruction
    assert "GAP-TV" in asked["s"]
