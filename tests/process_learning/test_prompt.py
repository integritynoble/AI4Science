from ai4science.harness.agents.process_learning.extract import parse_coverage_proposal
from ai4science.harness.agents.process_learning.prompt import (build_process_messages,
                                                              build_coverage_proposal_messages)
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState


def _fenced(p):
    return f"```json\n{p}\n```"


def test_parse_coverage_proposal_reused():
    a = parse_coverage_proposal(_fenced('{"action": "propose_coverage", "coverage_points": ["A","B"]}'))
    assert a == ["A", "B"]
    assert parse_coverage_proposal("no json") is None


def _state():
    return TaskState(task_id="t", contract=compile_contract(
        objective="x", capability_profile="A1", interaction_mode="I2"))


def test_build_process_messages_context():
    system, messages = build_process_messages(_state(), "run-42",
                                              ["why it retried"], ["trace/journal.md"])
    assert "explanation.md" in system
    assert "[S" in system and "## References" in system
    assert "never invent" in system.lower() or "not in the trace" in system.lower()
    assert "run-42" in messages[0]["content"]
    assert "why it retried" in messages[0]["content"] and "trace/journal.md" in messages[0]["content"]


def test_checklist_profile_differs():
    s1, _ = build_process_messages(_state(), "r", [], [], prompt_profile="terse")
    s2, _ = build_process_messages(_state(), "r", [], [], prompt_profile="checklist")
    assert s1 != s2


def test_coverage_proposal_messages():
    system, messages = build_coverage_proposal_messages("run-42", ["trace/journal.md"])
    assert "propose_coverage" in system and "run-42" in messages[0]["content"]
