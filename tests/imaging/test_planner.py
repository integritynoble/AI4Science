from ai4science.harness.agents.imaging.planner import ReferenceImagingPlanner
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState
from ai4science.harness.runtime.verifier import Verdict

def _state():
    return TaskState(task_id="t", contract=compile_contract(objective="x", capability_profile="A1"))

def test_first_step_is_flagged_reconstruction():
    # Both knobs are passed in, and both are asserted against what was passed. This
    # test set base_iters and then asserted the *default* tv_weight as a literal, so
    # correcting that default broke a test that is about the shape of the command.
    p = ReferenceImagingPlanner(base_iters=80, tv_weight=0.01)
    step = p.next_step(_state())
    assert step.flagged_kind == "preference_fork"           # dual-mode fork
    assert step.action_type == "sandbox_exec"
    assert step.command[:3] == ["python3", "code/run_solver.py", "--workspace"]
    assert "--iters" in step.command and "80" in step.command
    assert "--tv-weight" in step.command and "0.01" in step.command
    assert step.done is False

def test_defaults_are_the_settings_measured_to_work_on_real_scenes():
    """The shipped defaults must be the ones that pass, not the fixture's.

    80 iterations at tv_weight=0.01 over-smooths a real CAVE scene — forward
    residual 0.019 against a 0.003 noise floor, which `noise_consistency`
    rejects. 300 / 0.001 is the discrepancy-principle point and passes on
    seeds 42, 1 and 7. It is the default so that a caller who passes nothing
    gets a reconstruction that can pass."""
    step = ReferenceImagingPlanner().next_step(_state())
    assert "300" in step.command and "0.001" in step.command

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
