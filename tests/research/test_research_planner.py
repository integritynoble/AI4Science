from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState
from ai4science.harness.agents.research.planner import LLMResearchPlanner

def _resp(text):
    return {"ok": True, "response": {"content": [{"type": "text", "text": text}]}}

def _fenced(p):
    return f"```json\n{p}\n```"

class StubClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.requests = []
    def llm_egress(self, run_id, request):
        self.requests.append(request)
        return self._replies.pop(0)

def _state():
    return TaskState(task_id="t", contract=compile_contract(
        objective="q", capability_profile="A1", interaction_mode="I2"))

def _planner(client):
    return LLMResearchPlanner(client, "r1", question="q", coverage_points=["A"],
                              sources_index=["sources/a.txt"])

def test_step_maps_to_planstep():
    c = StubClient([_resp(_fenced(
        '{"action": "step", "summary": "draft", '
        '"stage_files": {"report.md": "# R\\n"}, "command": ["ls"]}'))])
    step = _planner(c).next_step(_state())
    assert step.stage_files == {"report.md": "# R\n"} and step.request_verify is False

def test_verify_and_blocked():
    assert _planner(StubClient([_resp(_fenced('{"action": "verify"}'))])).next_step(_state()).request_verify is True
    assert _planner(StubClient([_resp(_fenced('{"action": "blocked", "reason": "x"}'))])).next_step(_state()).done is True

def test_unusable_output_blocks():
    c = StubClient([_resp("junk")] * 3)
    assert LLMResearchPlanner(c, "r1", question="q", coverage_points=[], sources_index=[],
                              max_parse_retries=2).next_step(_state()).done is True

def test_request_shape_and_profile_threaded():
    c = StubClient([_resp(_fenced('{"action": "verify"}'))])
    LLMResearchPlanner(c, "r1", question="q", coverage_points=["A"],
                       sources_index=["sources/a.txt"], prompt_profile="checklist").next_step(_state())
    req = c.requests[0]
    assert "checklist" in req["system"].lower() or "check" in req["system"].lower()
    assert req["messages"][0]["role"] == "user"
