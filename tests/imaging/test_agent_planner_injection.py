import subprocess, sys
from pathlib import Path
from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep

class HostSimClient:
    def __init__(self, run_ws): self.run_ws = Path(run_ws); self.run_ws.mkdir(parents=True, exist_ok=True); self.executed = []
    def open_run(self, goal, cap, limits, interaction_profile="I1"):
        return {"run_id": "hs", "capability_profile": cap, "interaction_profile": interaction_profile,
                "limits": limits, "workspace_path": str(self.run_ws)}
    def stage_input(self, run_id, rel_path, content):
        d = self.run_ws / rel_path; d.parent.mkdir(parents=True, exist_ok=True); d.write_bytes(content); return {"ok": True}
    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": "ACT", "reason": "t"}
    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None, workspace_target=None):
        self.executed.append(command)
        p = subprocess.run([sys.executable] + command[1:], cwd=str(self.run_ws), capture_output=True, text=True)
        return {"exit_code": p.returncode, "is_error": p.returncode != 0, "timed_out": False, "artifacts": []}

class MarkerPlanner:
    def __init__(self): self.n = 0
    def next_step(self, state):
        self.n += 1
        if self.n == 1:
            return PlanStep(summary="marker", command=["python3", "-c", "open('marker.txt','w').write('x')"])
        return PlanStep(summary="deliver", command=[], done=True)
    def replan(self, state, verdict): pass

def test_injected_planner_is_used(tmp_path):
    client = HostSimClient(tmp_path / "runws")
    run_imaging_task(workspace=tmp_path / "seed", client=client, store=TaskStore(tmp_path / "t"),
                     task_id="inj", interaction_mode="I2", planner=MarkerPlanner())
    assert client.executed[0][:2] == ["python3", "-c"]          # the injected planner drove execution
    assert (client.run_ws / "marker.txt").exists()
