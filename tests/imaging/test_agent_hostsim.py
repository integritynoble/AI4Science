import subprocess, sys
from pathlib import Path
from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.runtime.task_store import TaskStore

class HostSimClient:
    """Models the control plane: open_run hands back a run workspace dir; stage_input writes
    into it; sandbox_execute runs the solver there; classify returns a fixed decision."""
    def __init__(self, run_ws: Path, decision="ACT"):
        self.run_ws = Path(run_ws); self.run_ws.mkdir(parents=True, exist_ok=True)
        self.decision = decision; self.executed = []
    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1"):
        return {"run_id": "hostsim", "capability_profile": capability_profile,
                "interaction_profile": interaction_profile, "limits": hard_limits,
                "workspace_path": str(self.run_ws)}
    def stage_input(self, run_id, rel_path, content):
        dest = self.run_ws / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return {"ok": True, "rel_path": rel_path}
    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": self.decision, "reason": "hostsim"}
    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None, workspace_target=None):
        self.executed.append(command)
        p = subprocess.run([sys.executable] + command[1:], cwd=str(self.run_ws),
                           capture_output=True, text=True)
        return {"exit_code": p.returncode, "is_error": p.returncode != 0,
                "timed_out": False, "stdout": p.stdout, "stderr": p.stderr, "artifacts": []}

def test_i2_delivers_physics_verified_reconstruction(tmp_path):
    client = HostSimClient(tmp_path / "runws", decision="ACT")
    out = run_imaging_task(workspace=tmp_path / "seed", client=client,
                           store=TaskStore(tmp_path / "tasks"), task_id="hs1",
                           interaction_mode="I2", seed=42, governed=False)
    assert out["status"] == "delivered", out
    assert client.executed and client.executed[0][1] == "code/run_solver.py"
    assert (client.run_ws / "results" / "reconstruction_xhat.npy").exists()   # produced in the run ws
    assert (client.run_ws / "code" / "run_solver.py").exists()                # inputs were staged
    assert not (client.run_ws / "data" / "ground_truth_x.npy").exists()       # answer key withheld from sandbox
    assert (client.run_ws / "data" / "measurement_y.npy").exists()            # but the measurement was staged

def test_i0_pauses_at_reconstruction_fork(tmp_path):
    client = HostSimClient(tmp_path / "runws", decision="ASK")
    asked = {}
    out = run_imaging_task(workspace=tmp_path / "seed", client=client,
                           store=TaskStore(tmp_path / "tasks"), task_id="hs2",
                           interaction_mode="I0", seed=42, governed=False,
                           on_ask=lambda step, state: asked.setdefault("s", step.summary))
    assert out["status"] == "awaiting_owner"
    assert client.executed == []
    assert not (client.run_ws / "results" / "reconstruction_xhat.npy").exists()
    assert "GAP-TV" in asked["s"]
