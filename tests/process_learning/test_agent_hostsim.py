import json
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.process_learning.agent import run_process_learning_task


class FakeClient:
    def __init__(self, classify="ACT", evaluate="pass", set_ok=True, stage_ok=True):
        self.classify_decision = classify
        self.evaluate_decision = evaluate
        self.set_ok = set_ok
        self.stage_ok = stage_ok
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
    def get_last_known_good(self, kind, name):
        return None
    def llm_egress(self, run_id, request):
        raise AssertionError("host-sim must not reach the LLM")


class ScriptedPlanner:
    def __init__(self):
        self._s = [PlanStep(summary="write", command=[],
                            stage_files={"explanation.md": "# Explanation\n"}, request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass


DEMAND = {"run_label": "run-42",
          "trace": {"journal.md": "step 1: ran solver; step 2: judge failed; step 3: retried and passed.\n"},
          "coverage_points": ["retry"]}


def test_supplied_coverage_delivers(tmp_path):
    client = FakeClient()
    out = run_process_learning_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                                    task_id="p1", interaction_mode="I2", planner=ScriptedPlanner())
    assert out["status"] == "delivered"
    assert "research_check.py" in client.staged and any(s.startswith("trace/") for s in client.staged)
    vc, ra = client.criteria_calls[0]
    assert vc[0][:3] == ["python3", "-I", "research_check.py"] and vc[0][3] == "--config"
    cfg = json.loads(vc[0][4])
    assert cfg["report"] == "explanation.md" and "trace/journal.md" in cfg["sources"]
    assert ra == ["explanation.md"]


def test_coverage_proposal_asks_in_i0(tmp_path):
    client = FakeClient(classify="ASK")
    out = run_process_learning_task(demand={"run_label": "r", "trace": {"j.md": "x\n"}},
                                    client=client, store=TaskStore(tmp_path), task_id="p2",
                                    interaction_mode="I0", propose=lambda c, rid, rl, ti, m: ["retry"])
    assert out["status"] == "awaiting_owner" and out["proposed_coverage"] == ["retry"]
    assert client.criteria_calls == []


def test_failing_gate_never_delivers(tmp_path):
    client = FakeClient(evaluate="fail")
    steps = [PlanStep(summary="w", command=[], stage_files={"explanation.md": "# E\n"}, request_verify=False),
             PlanStep(summary="v", command=[], request_verify=True),
             PlanStep(summary="give up", command=[], done=True)]
    class P:
        def next_step(self, state): return steps.pop(0)
        def replan(self, state, verdict): pass
    out = run_process_learning_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                                    task_id="p3", interaction_mode="I2", planner=P())
    assert out["status"] == "blocked"
