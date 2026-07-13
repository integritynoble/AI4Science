import json
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState
from ai4science.harness.agents.work.prompt import (build_work_messages,
                                                   build_criteria_messages,
                                                   JOURNAL_TAIL)

def _state(journal=()):
    contract = compile_contract(objective="fix add() in calc.py",
                                capability_profile="A1", interaction_mode="I2",
                                constraints=["keep the public API"])
    st = TaskState(task_id="t", contract=contract)
    st.journal = list(journal)
    return st

CRITERIA = {"verify_commands": [["python3", "check.py"]], "required_artifacts": ["calc.py"]}

def test_system_contains_protocol_and_criteria():
    system, messages = build_work_messages(_state(), CRITERIA)
    assert '"action"' in system                       # the step protocol is spelled out
    assert "no network" in system.lower()
    assert json.dumps(CRITERIA["verify_commands"]) in system
    assert messages[0]["role"] == "user"

def test_user_contains_objective_constraints_and_journal_tail():
    entries = [{"plan": f"step {i}", "failed": False, "exit_code": 0,
                "stdout_tail": f"out{i}", "stderr_tail": ""} for i in range(JOURNAL_TAIL + 5)]
    system, messages = build_work_messages(_state(entries), CRITERIA)
    user = messages[0]["content"]
    assert "fix add() in calc.py" in user
    assert "keep the public API" in user
    assert f"step {JOURNAL_TAIL + 4}" in user          # newest entry present
    assert "step 0" not in user                        # older-than-tail entries dropped

def test_last_feedback_is_included_verbatim():
    fb = {"commands": [{"index": 0, "exit_code": 1, "stderr_tail": "AssertionError: 2 != 3",
                        "timed_out": False}], "missing_artifacts": []}
    system, messages = build_work_messages(_state(), CRITERIA, last_feedback=fb)
    assert "AssertionError: 2 != 3" in messages[0]["content"]

def test_criteria_messages_mention_objective_and_files():
    system, messages = build_criteria_messages("analyze sales.csv", ["sales.csv", "notes.md"])
    assert "propose_criteria" in system
    assert "analyze sales.csv" in messages[0]["content"]
    assert "sales.csv" in messages[0]["content"]
