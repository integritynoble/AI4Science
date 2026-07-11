from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.verifier import Verdict
from ai4science.harness.runtime.pev import run_task, PlanStep, detect_boundary

class FakeClient:
    def __init__(self, decision="ACT"): self.decision = decision; self.executed = []
    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": self.decision, "reason": "test"}
    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None, workspace_target=None):
        self.executed.append(command); return {"exit_code": 0, "is_error": False, "artifacts": ["out.npy"]}

class OneStepPlanner:
    def __init__(self): self.calls = 0
    def next_step(self, state):
        self.calls += 1
        return PlanStep(summary="compute", command=["true"])
    def replan(self, state, verdict): pass

class CompleteVerifier:
    def check(self, result, contract): return Verdict(complete=True, repairable=False)

class NeverCompleteVerifier:
    def __init__(self): self.n = 0
    def check(self, result, contract):
        self.n += 1
        return Verdict(complete=False, repairable=self.n < 2)  # repair once, then blocker

def _contract(mode="I2"):
    return compile_contract(objective="x", capability_profile="A1", interaction_mode=mode)

def test_detect_boundary_external_from_action_type():
    s = PlanStep(summary="post", command=["x"], action_type="publish")
    from ai4science.harness.runtime.task_store import TaskState
    st = TaskState(task_id="t", contract=_contract())
    assert detect_boundary(s, st) == "irreversible_or_external"

def test_delivered_on_act_and_complete(tmp_path):
    client = FakeClient("ACT")
    out = run_task(run_id="r", contract=_contract(), client=client, planner=OneStepPlanner(),
                   verifier=CompleteVerifier(), store=TaskStore(Path(tmp_path)), task_id="t1")
    assert out["status"] == "delivered" and client.executed == [["true"]]

def test_ask_pauses_without_executing(tmp_path):
    client = FakeClient("ASK")
    asked = {}
    out = run_task(run_id="r", contract=_contract(), client=client, planner=OneStepPlanner(),
                   verifier=CompleteVerifier(), store=TaskStore(Path(tmp_path)), task_id="t2",
                   on_ask=lambda step, state: asked.setdefault("k", step.summary))
    assert out["status"] == "awaiting_owner" and client.executed == []

def test_deny_blocks_without_executing(tmp_path):
    client = FakeClient("DENY")
    out = run_task(run_id="r", contract=_contract(), client=client, planner=OneStepPlanner(),
                   verifier=CompleteVerifier(), store=TaskStore(Path(tmp_path)), task_id="t3")
    assert out["status"] == "blocked" and client.executed == []

def test_repair_then_blocker(tmp_path):
    out = run_task(run_id="r", contract=_contract(), client=FakeClient("ACT"), planner=OneStepPlanner(),
                   verifier=NeverCompleteVerifier(), store=TaskStore(Path(tmp_path)), task_id="t4")
    assert out["status"] == "blocked"

def test_unknown_action_type_is_not_routine():
    from ai4science.harness.runtime.task_store import TaskState
    st = TaskState(task_id="t", contract=_contract())
    assert detect_boundary(PlanStep(summary="wire funds", command=["x"], action_type="wire_transfer"), st) == "irreversible_or_external"
    assert detect_boundary(PlanStep(summary="x", command=["x"], action_type=None), st) == "irreversible_or_external"
    assert detect_boundary(PlanStep(summary="x", command=["x"]), st) == "routine"  # default sandbox_exec

def test_unexpected_decision_fails_closed(tmp_path):
    from pathlib import Path
    client = FakeClient("WAT")   # not ACT/ASK/DENY
    out = run_task(run_id="r", contract=_contract(), client=client, planner=OneStepPlanner(),
                   verifier=CompleteVerifier(), store=TaskStore(Path(tmp_path)), task_id="tf")
    assert out["status"] == "blocked" and client.executed == []

def test_planner_done_without_completion_is_blocked(tmp_path):
    from pathlib import Path
    class GiveUpPlanner:
        def next_step(self, state):
            return PlanStep(summary="give up", command=[], done=True)
        def replan(self, state, verdict): pass
    out = run_task(run_id="r", contract=_contract(), client=FakeClient("ACT"),
                   planner=GiveUpPlanner(), verifier=CompleteVerifier(),
                   store=TaskStore(Path(tmp_path)), task_id="gu")
    assert out["status"] == "blocked"

def test_resume_finished_reports_final_status(tmp_path):
    from pathlib import Path
    store = TaskStore(Path(tmp_path))
    args = dict(run_id="r", contract=_contract(), client=FakeClient("ACT"), planner=OneStepPlanner(),
                verifier=CompleteVerifier(), store=store, task_id="tr")
    first = run_task(**args)
    assert first["status"] == "delivered"
    again = run_task(**{**args, "planner": OneStepPlanner()})
    assert again["status"] == "delivered" and again.get("resumed") is True
