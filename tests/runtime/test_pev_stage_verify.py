from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.verifier import Verdict
from ai4science.harness.runtime.pev import run_task, PlanStep

class FakeClient:
    """ACT-everything client that records staging and execution order."""
    def __init__(self, stage_ok=True):
        self.stage_ok = stage_ok
        self.staged = []          # (rel_path, content_bytes)
        self.executed = []        # command lists
        self.order = []           # "stage:<rel>" / "exec:<argv0>"
    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": "ACT", "reason": "test"}
    def stage_input(self, run_id, rel_path, content):
        self.staged.append((rel_path, content))
        self.order.append(f"stage:{rel_path}")
        return {"ok": self.stage_ok, "reason": "" if self.stage_ok else "path confinement"}
    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None,
                        workspace_target=None):
        self.executed.append(command)
        self.order.append(f"exec:{command[0]}")
        return {"exit_code": 0, "is_error": False, "stdout": "OUT" * 2000, "stderr": "E"}

class ScriptedPlanner:
    def __init__(self, steps):
        self._steps = list(steps)
    def next_step(self, state):
        return self._steps.pop(0)
    def replan(self, state, verdict):
        pass

class CountingVerifier:
    def __init__(self, complete=True):
        self.calls = 0
        self._complete = complete
    def check(self, result, contract):
        self.calls += 1
        return Verdict(complete=self._complete, repairable=not self._complete)

def _contract():
    return compile_contract(objective="x", capability_profile="A1", interaction_mode="I2")

def test_stage_files_staged_before_execute(tmp_path):
    client = FakeClient()
    steps = [PlanStep(summary="write+run", command=["python3", "x.py"],
                      stage_files={"x.py": "print(1)\n"})]
    out = run_task(run_id="r", contract=_contract(), client=client,
                   planner=ScriptedPlanner(steps), verifier=CountingVerifier(True),
                   store=TaskStore(Path(tmp_path)), task_id="t1")
    assert out["status"] == "delivered"
    assert client.staged == [("x.py", b"print(1)\n")]
    assert client.order == ["stage:x.py", "exec:python3"]

def test_stage_input_refusal_blocks_without_executing(tmp_path):
    client = FakeClient(stage_ok=False)
    steps = [PlanStep(summary="write", command=["python3", "x.py"],
                      stage_files={"../evil": "x"})]
    out = run_task(run_id="r", contract=_contract(), client=client,
                   planner=ScriptedPlanner(steps), verifier=CountingVerifier(True),
                   store=TaskStore(Path(tmp_path)), task_id="t2")
    assert out["status"] == "blocked"
    assert client.executed == []

def test_empty_command_skips_sandbox_execute(tmp_path):
    client = FakeClient()
    steps = [PlanStep(summary="verify only", command=[])]
    out = run_task(run_id="r", contract=_contract(), client=client,
                   planner=ScriptedPlanner(steps), verifier=CountingVerifier(True),
                   store=TaskStore(Path(tmp_path)), task_id="t3")
    assert out["status"] == "delivered"
    assert client.executed == []

def test_request_verify_false_skips_verifier_and_continues(tmp_path):
    client = FakeClient()
    verifier = CountingVerifier(True)
    steps = [PlanStep(summary="edit", command=["true"], request_verify=False),
             PlanStep(summary="verify", command=[], request_verify=True)]
    out = run_task(run_id="r", contract=_contract(), client=client,
                   planner=ScriptedPlanner(steps), verifier=verifier,
                   store=TaskStore(Path(tmp_path)), task_id="t4")
    assert out["status"] == "delivered"
    assert verifier.calls == 1          # only the request_verify step was verified

def test_default_request_verify_preserves_per_step_verification(tmp_path):
    client = FakeClient()
    verifier = CountingVerifier(True)
    steps = [PlanStep(summary="compute", command=["true"])]
    out = run_task(run_id="r", contract=_contract(), client=client,
                   planner=ScriptedPlanner(steps), verifier=verifier,
                   store=TaskStore(Path(tmp_path)), task_id="t5")
    assert out["status"] == "delivered"
    assert verifier.calls == 1          # unchanged imaging-era behavior

def test_journal_records_output_tails(tmp_path):
    client = FakeClient()
    store = TaskStore(Path(tmp_path))
    steps = [PlanStep(summary="compute", command=["true"])]
    run_task(run_id="r", contract=_contract(), client=client,
             planner=ScriptedPlanner(steps), verifier=CountingVerifier(True),
             store=store, task_id="t6")
    state = store.resume("t6")
    entry = state.journal[0]
    assert entry["exit_code"] == 0
    assert entry["stderr_tail"] == "E"
    assert len(entry["stdout_tail"]) == 2000     # capped
