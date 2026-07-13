from ai4science.harness.agents.research.extract import parse_coverage_proposal
from ai4science.harness.agents.research.prompt import (build_research_messages,
                                                      build_coverage_proposal_messages)
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState

def _fenced(payload):
    return f"reasoning\n```json\n{payload}\n```\n"

def test_parse_coverage_proposal():
    a = parse_coverage_proposal(_fenced('{"action": "propose_coverage", "coverage_points": ["A", "B"]}'))
    assert a == ["A", "B"]
    assert parse_coverage_proposal(_fenced('{"action": "propose_coverage", "coverage_points": []}')) is None
    assert parse_coverage_proposal(_fenced('{"action": "propose_coverage", "coverage_points": [1]}')) is None
    assert parse_coverage_proposal("no json") is None
    assert parse_coverage_proposal(_fenced('{"action": "other"}')) is None

def _state():
    return TaskState(task_id="t", contract=compile_contract(
        objective="research q", capability_profile="A1", interaction_mode="I2"))

def test_build_research_messages_includes_context():
    system, messages = build_research_messages(
        _state(), "Why is the sky blue?", ["cause", "wavelengths"],
        ["sources/a.txt", "sources/b.txt"])
    assert "[S" in system                        # citation convention in the prompt
    assert "## References" in system
    assert "Why is the sky blue?" in messages[0]["content"]
    assert "cause" in messages[0]["content"] and "sources/a.txt" in messages[0]["content"]

def test_build_research_messages_checklist_profile_differs():
    s_terse, _ = build_research_messages(_state(), "q", [], [], prompt_profile="terse")
    s_check, _ = build_research_messages(_state(), "q", [], [], prompt_profile="checklist")
    assert s_terse != s_check

def test_coverage_proposal_messages():
    system, messages = build_coverage_proposal_messages("Why is the sky blue?", ["sources/a.txt"])
    assert "propose_coverage" in system
    assert "Why is the sky blue?" in messages[0]["content"]
