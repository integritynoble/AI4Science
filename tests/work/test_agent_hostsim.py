"""Agent-logic tests with a fake control-plane client (no podman, no LLM)."""
from pathlib import Path
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.work.agent import run_work_task

class FakeWorkClient:
    def __init__(self, classify_decision="ACT", evaluate_decision="pass",
                 set_criteria_ok=True, stage_ok=True):
        self.classify_decision = classify_decision
        self.evaluate_decision = evaluate_decision
        self.set_criteria_ok = set_criteria_ok
        self.stage_ok = stage_ok
        self.staged, self.criteria_calls, self.executed = [], [], []
    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1"):
        return {"run_id": "r1", "capability_profile": capability_profile,
                "interaction_profile": interaction_profile, "limits": hard_limits,
                "workspace_path": "/tmp/fake-ws"}
    def stage_input(self, run_id, rel_path, content):
        self.staged.append((rel_path, content))
        return {"ok": self.stage_ok}
    def set_criteria(self, run_id, verify_commands, required_artifacts):
        self.criteria_calls.append((verify_commands, required_artifacts))
        return {"ok": self.set_criteria_ok,
                "reason": "" if self.set_criteria_ok else "criteria already set"}
    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": self.classify_decision, "reason": "test"}
    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None,
                        workspace_target=None):
        self.executed.append(command)
        return {"exit_code": 0, "is_error": False, "stdout": "", "stderr": ""}
    def evaluate(self, run_id, domain="cassi"):
        return {"decision": self.evaluate_decision, "score": 0.0, "feedback": {}}
    def llm_egress(self, run_id, request):
        raise AssertionError("host-sim tests must not reach the LLM")

class ScriptedPlanner:
    def __init__(self, steps):
        self._steps = list(steps)
    def next_step(self, state):
        return self._steps.pop(0)
    def replan(self, state, verdict):
        pass

DEMAND = {"objective": "fix calc.py",
          "input_files": {"calc.py": "def add(a,b): return a-b\n"},
          "verify_commands": [["python3", "check.py"]],
          "required_artifacts": ["calc.py"]}

def _steps():
    return [PlanStep(summary="fix", command=["python3", "-c", "pass"],
                     stage_files={"calc.py": "def add(a,b): return a+b\n"},
                     request_verify=False),
            PlanStep(summary="verify success criteria", command=[], request_verify=True)]

def test_supplied_criteria_delivers(tmp_path):
    client = FakeWorkClient()
    out = run_work_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                        task_id="w1", interaction_mode="I2", planner=ScriptedPlanner(_steps()))
    assert out["status"] == "delivered"
    assert client.criteria_calls == [([["python3", "check.py"]], ["calc.py"])]
    assert ("calc.py", b"def add(a,b): return a-b\n") in client.staged   # input staged

def test_set_criteria_refusal_blocks(tmp_path):
    client = FakeWorkClient(set_criteria_ok=False)
    out = run_work_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                        task_id="w2", interaction_mode="I2", planner=ScriptedPlanner(_steps()))
    assert out["status"] == "blocked" and "set_criteria" in out["why"]

def test_stage_input_refusal_blocks(tmp_path):
    client = FakeWorkClient(stage_ok=False)
    out = run_work_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                        task_id="w3", interaction_mode="I2", planner=ScriptedPlanner(_steps()))
    assert out["status"] == "blocked"

def test_proposal_asks_in_interactive_mode(tmp_path):
    client = FakeWorkClient(classify_decision="ASK")
    proposal = {"verify_commands": [["python3", "check.py"]], "required_artifacts": []}
    out = run_work_task(demand={"objective": "fix calc.py",
                                "input_files": {"calc.py": "x"}},
                        client=client, store=TaskStore(tmp_path), task_id="w4",
                        interaction_mode="I0",
                        propose=lambda client, run_id, objective, input_files, model: proposal)
    assert out["status"] == "awaiting_owner"
    assert out["proposed_criteria"] == proposal
    assert client.criteria_calls == []                 # nothing registered before approval

def test_proposal_acts_and_records_assumption_in_i2(tmp_path):
    client = FakeWorkClient(classify_decision="ACT")
    store = TaskStore(tmp_path)
    proposal = {"verify_commands": [["python3", "check.py"]], "required_artifacts": []}
    out = run_work_task(demand={"objective": "fix calc.py"},
                        client=client, store=store, task_id="w5",
                        interaction_mode="I2",
                        propose=lambda client, run_id, objective, input_files, model: proposal,
                        planner=ScriptedPlanner(_steps()))
    assert out["status"] == "delivered"
    assert client.criteria_calls == [([["python3", "check.py"]], [])]
    state = store.resume("w5")
    assert any("criteria" in a.get("assumption", "") for a in state.assumptions)

def test_unusable_proposal_blocks(tmp_path):
    client = FakeWorkClient()
    out = run_work_task(demand={"objective": "vague"},
                        client=client, store=TaskStore(tmp_path), task_id="w6",
                        interaction_mode="I2",
                        propose=lambda client, run_id, objective, input_files, model: None)
    assert out["status"] == "blocked" and "criteria" in out["why"]

def test_failing_criteria_never_delivers(tmp_path):
    client = FakeWorkClient(evaluate_decision="fail")
    steps = _steps() + [PlanStep(summary="give up", command=[], done=True)]
    out = run_work_task(demand=DEMAND, client=client, store=TaskStore(tmp_path),
                        task_id="w7", interaction_mode="I2", planner=ScriptedPlanner(steps))
    assert out["status"] == "blocked"
