import json
from pathlib import Path
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.learning.agent import run_learning_task

class FakeClient:
    def __init__(self, classify="ACT", evaluate="pass", set_ok=True, stage_ok=True):
        self.classify_decision = classify; self.evaluate_decision = evaluate
        self.set_ok = set_ok; self.stage_ok = stage_ok
        self.staged, self.criteria_calls = [], []
    def open_run(self, goal, cap, limits, interaction_profile="I1"):
        return {"run_id": "r1", "workspace_path": "/tmp/x", "limits": limits,
                "capability_profile": cap, "interaction_profile": interaction_profile}
    def stage_input(self, run_id, rel, content):
        self.staged.append(rel); return {"ok": self.stage_ok}
    def set_criteria(self, run_id, vc, ra):
        self.criteria_calls.append((vc, ra)); return {"ok": self.set_ok, "reason": "x"}
    def classify(self, run_id, kind, *, step_summary="", action_type=None):
        return {"decision": self.classify_decision}
    def sandbox_execute(self, run_id, command, **kw):
        return {"exit_code": 0, "is_error": False, "stdout": "", "stderr": ""}
    def evaluate(self, run_id, domain="cassi"):
        return {"decision": self.evaluate_decision, "feedback": {}}
    def get_last_known_good(self, kind, name): return None
    def llm_egress(self, run_id, request):
        raise AssertionError("host-sim must not reach the LLM")

class ScriptedPlanner:
    def __init__(self):
        self._s = [PlanStep(summary="write", command=[],
                            stage_files={"study_guide.md": "# G\n", "quiz.json": "{}"},
                            request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass

DEMAND = {"topic": "cell biology",
          "material": {"m.txt": "Photosynthesis occurs in the chloroplast.\n"},
          "coverage_points": ["photosynthesis"]}

def test_supplied_coverage_delivers(tmp_path):
    client = FakeClient()
    out = run_learning_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                            task_id="l1", interaction_mode="I2", planner=ScriptedPlanner())
    assert out["status"] == "delivered"
    assert "quiz_check.py" in client.staged and "research_spec.json" not in client.staged
    assert any(s.startswith("material/") for s in client.staged)
    vc, ra = client.criteria_calls[0]
    assert vc[0][:3] == ["python3", "-I", "quiz_check.py"] and vc[0][3] == "--config"
    cfg = json.loads(vc[0][4])
    assert cfg["min_questions"] >= 1 and "material/m.txt" in cfg["sources"]
    assert set(ra) == {"study_guide.md", "quiz.json"}

def test_coverage_proposal_asks_in_i0(tmp_path):
    client = FakeClient(classify="ASK")
    out = run_learning_task(demand={"topic": "t", "material": {"m.txt": "x\n"}},
                            client=client, store=TaskStore(tmp_path), task_id="l2",
                            interaction_mode="I0", propose=lambda c, rid, t, si, m: ["photosynthesis"])
    assert out["status"] == "awaiting_owner" and out["proposed_coverage"] == ["photosynthesis"]
    assert client.criteria_calls == []

def test_failing_gate_never_delivers(tmp_path):
    client = FakeClient(evaluate="fail")
    steps = [PlanStep(summary="w", command=[], stage_files={"study_guide.md": "# G\n", "quiz.json": "{}"}, request_verify=False),
             PlanStep(summary="v", command=[], request_verify=True),
             PlanStep(summary="give up", command=[], done=True)]
    class P:
        def next_step(self, state): return steps.pop(0)
        def replan(self, state, verdict): pass
    out = run_learning_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                            task_id="l3", interaction_mode="I2", planner=P())
    assert out["status"] == "blocked"
