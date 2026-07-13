from pathlib import Path
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.work.agent import run_work_task

class RecordingClient:
    """Captures the max_steps budget and the planner's prompt_profile."""
    def __init__(self, lkg_metadata=None):
        self._lkg = lkg_metadata
        self.open_limits = None
    def get_last_known_good(self, kind, name):
        return {"metadata": self._lkg} if self._lkg else None
    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1"):
        self.open_limits = hard_limits
        return {"run_id": "r1", "workspace_path": "/tmp/x", "limits": hard_limits,
                "capability_profile": capability_profile, "interaction_profile": interaction_profile}
    def stage_input(self, run_id, rel, content): return {"ok": True}
    def set_criteria(self, run_id, vc, ra): return {"ok": True}
    def classify(self, run_id, kind, *, step_summary="", action_type=None):
        return {"decision": "ACT"}
    def sandbox_execute(self, run_id, command, **kw):
        return {"exit_code": 0, "is_error": False, "stdout": "", "stderr": ""}
    def evaluate(self, run_id, domain="cassi"):
        return {"decision": "pass", "feedback": {}}

DEMAND = {"objective": "o", "input_files": {}, "verify_commands": [["true"]],
          "required_artifacts": []}

def _oneshot():
    return [PlanStep(summary="v", command=[], request_verify=True)]

class ScriptedPlanner:
    def __init__(self, steps): self._s = list(steps)
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass

def test_no_promotion_uses_default_budget(tmp_path):
    client = RecordingClient(lkg_metadata=None)
    run_work_task(demand=DEMAND, client=client, store=TaskStore(tmp_path), task_id="w1",
                  interaction_mode="I2", planner=ScriptedPlanner(_oneshot()))
    assert client.open_limits["actions"] == 20 + 5        # default max_steps 20

def test_promoted_config_adopts_max_steps(tmp_path):
    client = RecordingClient(lkg_metadata={"prompt_profile": "checklist", "max_steps": 8})
    run_work_task(demand=DEMAND, client=client, store=TaskStore(tmp_path), task_id="w2",
                  interaction_mode="I2", planner=ScriptedPlanner(_oneshot()))
    assert client.open_limits["actions"] == 8 + 5         # adopted promoted max_steps
