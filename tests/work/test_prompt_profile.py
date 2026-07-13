from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState
from ai4science.harness.agents.work.prompt import build_work_messages

def _state():
    return TaskState(task_id="t", contract=compile_contract(
        objective="x", capability_profile="A1", interaction_mode="I2"))

CRIT = {"verify_commands": [["true"]], "required_artifacts": []}

def test_terse_is_default_and_backward_compatible():
    sys_default, _ = build_work_messages(_state(), CRIT)
    sys_terse, _ = build_work_messages(_state(), CRIT, prompt_profile="terse")
    assert sys_default == sys_terse                       # default unchanged

def test_checklist_profile_adds_directive():
    sys_terse, _ = build_work_messages(_state(), CRIT, prompt_profile="terse")
    sys_check, _ = build_work_messages(_state(), CRIT, prompt_profile="checklist")
    assert sys_check != sys_terse
    assert "checklist" in sys_check.lower()
