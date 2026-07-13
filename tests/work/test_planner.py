import json
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState
from ai4science.harness.runtime.verifier import Verdict
from ai4science.harness.agents.work.planner import LLMWorkPlanner, DEFAULT_MODEL

CRITERIA = {"verify_commands": [["python3", "check.py"]], "required_artifacts": []}

def _resp(text):
    return {"ok": True, "response": {"content": [{"type": "text", "text": text}]}}

def _fenced(payload: str) -> str:
    return f"```json\n{payload}\n```"

class StubClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.requests = []
    def llm_egress(self, run_id, request):
        self.requests.append((run_id, request))
        return self._replies.pop(0)

def _state():
    return TaskState(task_id="t", contract=compile_contract(
        objective="x", capability_profile="A1", interaction_mode="I2"))

def test_step_action_maps_to_planstep_without_verification():
    client = StubClient([_resp(_fenced(
        '{"action": "step", "summary": "write calc", '
        '"stage_files": {"calc.py": "def add(a,b): return a+b\\n"}, '
        '"command": ["python3", "calc.py"]}'))])
    step = LLMWorkPlanner(client, "r1", criteria=CRITERIA).next_step(_state())
    assert step.summary == "write calc"
    assert step.stage_files == {"calc.py": "def add(a,b): return a+b\n"}
    assert step.command == ["python3", "calc.py"]
    assert step.request_verify is False
    assert step.done is False

def test_verify_action_maps_to_verify_step():
    client = StubClient([_resp(_fenced('{"action": "verify"}'))])
    step = LLMWorkPlanner(client, "r1", criteria=CRITERIA).next_step(_state())
    assert step.command == [] and step.request_verify is True and step.done is False

def test_blocked_action_maps_to_done_step():
    client = StubClient([_resp(_fenced('{"action": "blocked", "reason": "impossible"}'))])
    step = LLMWorkPlanner(client, "r1", criteria=CRITERIA).next_step(_state())
    assert step.done is True and "impossible" in step.summary

def test_malformed_output_retries_then_blocks():
    client = StubClient([_resp("garbage"), _resp("also garbage"), _resp("still garbage")])
    planner = LLMWorkPlanner(client, "r1", criteria=CRITERIA, max_parse_retries=2)
    step = planner.next_step(_state())
    assert step.done is True                      # honest blocker, no fabricated step
    assert len(client.requests) == 3              # initial + 2 retries

def test_llm_egress_failure_counts_as_parse_failure():
    client = StubClient([{"ok": False, "reason": "budget exceeded"}] * 3)
    planner = LLMWorkPlanner(client, "r1", criteria=CRITERIA, max_parse_retries=2)
    assert planner.next_step(_state()).done is True

def test_replan_feedback_reaches_next_prompt():
    fb = {"commands": [{"index": 0, "exit_code": 1,
                        "stderr_tail": "AssertionError: 2 != 3", "timed_out": False}]}
    client = StubClient([_resp(_fenced('{"action": "verify"}'))])
    planner = LLMWorkPlanner(client, "r1", criteria=CRITERIA)
    planner.replan(_state(), Verdict(complete=False, repairable=True,
                                     evidence={"decision": "fail", "feedback": fb}))
    planner.next_step(_state())
    request = client.requests[0][1]
    assert "AssertionError: 2 != 3" in request["messages"][0]["content"]

def test_request_shape_is_anthropic_messages():
    client = StubClient([_resp(_fenced('{"action": "verify"}'))])
    LLMWorkPlanner(client, "r1", criteria=CRITERIA).next_step(_state())
    run_id, request = client.requests[0]
    assert run_id == "r1"
    assert request["model"] == DEFAULT_MODEL
    assert isinstance(request["max_tokens"], int)
    assert isinstance(request["system"], str)
    assert request["messages"][0]["role"] == "user"
