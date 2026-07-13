import json
from pathlib import Path
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.research.agent import run_research_task

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
        self._s = [PlanStep(summary="write", command=[], stage_files={"report.md": "# R\n"},
                            request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass

DEMAND = {"question": "Why is the sky blue?",
          "sources": {"a.txt": "Rayleigh scattering of sunlight.\n"},
          "coverage_points": ["cause"]}

def test_supplied_coverage_delivers(tmp_path):
    client = FakeClient()
    out = run_research_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                            task_id="r1", interaction_mode="I2", planner=ScriptedPlanner())
    assert out["status"] == "delivered"
    # research_check.py, question.txt, sources/a.txt staged; NO research_spec.json
    assert "research_check.py" in client.staged
    assert "research_spec.json" not in client.staged
    assert any(s.startswith("sources/") for s in client.staged)
    # grounding verify command carries the CP-private config in argv
    vc, ra = client.criteria_calls[0]
    assert vc[0][:3] == ["python3", "-I", "research_check.py"]
    assert vc[0][3] == "--config"
    cfg = json.loads(vc[0][4])
    assert cfg["report"] == "report.md" and "sources/a.txt" in cfg["sources"]
    assert len(cfg["sources"]["sources/a.txt"]) == 64          # sha256 hex
    assert cfg["coverage_points"] == ["cause"] and ra == ["report.md"]

def test_coverage_proposal_asks_in_i0(tmp_path):
    client = FakeClient(classify="ASK")
    demand = {"question": "q", "sources": {"a.txt": "x\n"}}   # no coverage_points
    out = run_research_task(demand=demand, client=client, store=TaskStore(tmp_path),
                            task_id="r2", interaction_mode="I0",
                            propose=lambda c, rid, q, si, m: ["cause"])
    assert out["status"] == "awaiting_owner"
    assert out["proposed_coverage"] == ["cause"]
    assert client.criteria_calls == []       # nothing registered before approval

def test_coverage_proposal_acts_in_i2(tmp_path):
    client = FakeClient(classify="ACT")
    demand = {"question": "q", "sources": {"a.txt": "x\n"}}
    out = run_research_task(demand=demand, client=client, store=TaskStore(tmp_path),
                            task_id="r3", interaction_mode="I2",
                            propose=lambda c, rid, q, si, m: ["cause"], planner=ScriptedPlanner())
    assert out["status"] == "delivered" and client.criteria_calls

def test_unusable_proposal_blocks(tmp_path):
    client = FakeClient()
    out = run_research_task(demand={"question": "q", "sources": {}}, client=client,
                            store=TaskStore(tmp_path), task_id="r4", interaction_mode="I2",
                            propose=lambda c, rid, q, si, m: None)
    assert out["status"] == "blocked"

def test_set_criteria_refusal_blocks(tmp_path):
    client = FakeClient(set_ok=False)
    out = run_research_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                            task_id="r5", interaction_mode="I2", planner=ScriptedPlanner())
    assert out["status"] == "blocked"

def test_failing_grounding_never_delivers(tmp_path):
    client = FakeClient(evaluate="fail")
    steps = [PlanStep(summary="write", command=[], stage_files={"report.md": "# R\n"}, request_verify=False),
             PlanStep(summary="verify", command=[], request_verify=True),
             PlanStep(summary="give up", command=[], done=True)]
    class P:
        def next_step(self, state): return steps.pop(0)
        def replan(self, state, verdict): pass
    out = run_research_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                            task_id="r6", interaction_mode="I2", planner=P())
    assert out["status"] == "blocked"
