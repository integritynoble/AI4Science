from ai4science.harness.agents.learning.extract import parse_coverage_proposal
from ai4science.harness.agents.learning.prompt import (build_learning_messages,
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

def test_build_learning_messages_context():
    system, messages = build_learning_messages(_state(), "cell biology",
                                               ["mitochondria"], ["material/m.txt"])
    assert "quiz.json" in system and "study_guide.md" in system
    assert "grounding" in system.lower()          # requires a verbatim grounding span
    assert "cell biology" in messages[0]["content"]
    assert "mitochondria" in messages[0]["content"] and "material/m.txt" in messages[0]["content"]

def test_checklist_profile_differs():
    s1, _ = build_learning_messages(_state(), "t", [], [], prompt_profile="terse")
    s2, _ = build_learning_messages(_state(), "t", [], [], prompt_profile="checklist")
    assert s1 != s2

def test_coverage_proposal_messages():
    system, messages = build_coverage_proposal_messages("cell biology", ["material/m.txt"])
    assert "propose_coverage" in system and "cell biology" in messages[0]["content"]
