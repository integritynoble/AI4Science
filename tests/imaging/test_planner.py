from ai4science.harness.agents.imaging.planner import ReferenceImagingPlanner
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState
from ai4science.harness.runtime.verifier import Verdict

def _state():
    return TaskState(task_id="t", contract=compile_contract(objective="x", capability_profile="A1"))

def test_first_step_is_flagged_reconstruction():
    p = ReferenceImagingPlanner(base_iters=80)
    step = p.next_step(_state())
    assert step.flagged_kind == "preference_fork"           # dual-mode fork
    assert step.action_type == "sandbox_exec"
    assert step.command[:3] == ["python3", "code/run_solver.py", "--workspace"]
    assert "--iters" in step.command and "80" in step.command
    assert "--tv-weight" in step.command and "0.01" in step.command
    assert step.done is False

def test_replan_repairable_bumps_iters():
    p = ReferenceImagingPlanner(base_iters=80, iter_step=80, max_repairs=2)
    p.next_step(_state())
    p.replan(_state(), Verdict(complete=False, repairable=True))
    step = p.next_step(_state())
    assert "160" in step.command                             # 80 + 80

def test_gives_up_after_max_repairs():
    p = ReferenceImagingPlanner(base_iters=80, max_repairs=1)
    st = _state()
    p.next_step(st)
    p.replan(st, Verdict(complete=False, repairable=True))   # attempt 1
    p.next_step(st)
    p.replan(st, Verdict(complete=False, repairable=True))   # attempt 2 > max_repairs=1
    step = p.next_step(st)
    assert step.done is True                                 # stop retrying → loop reports blocker
