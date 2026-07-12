from ai4science.harness.agents.imaging.llm.planner import LLMImagingPlanner
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.runtime.verifier import Verdict

SOLVERS = [{"key": "traditional_cpu", "name": "GAP-TV", "reference": "",
            "cfg": {"iters": 100, "lam": 0.1, "tv_iter": 5}},
           {"key": "best_quality", "name": "GAP-TV (200 iter)", "reference": "",
            "cfg": {"iters": 200, "lam": 0.01, "tv_iter": 5}}]

def _state():
    st = TaskState(task_id="t", contract=compile_contract(objective="reconstruct", capability_profile="A1"))
    st.journal = []
    return st

def _stub(*keys):
    return StubAdapter([[TextDelta(text=f'```json\n{{"solver": "{k}"}}\n```')] for k in keys])

class FallbackSpy:
    def __init__(self): self.next_called = 0; self.replan_called = 0
    def next_step(self, state):
        self.next_called += 1
        return PlanStep(summary="GAP-TV fallback", command=["python3", "code/run_solver.py"])
    def replan(self, state, verdict): self.replan_called += 1

def test_selected_solver_becomes_a_configured_step():
    p = LLMImagingPlanner(_stub("best_quality"), model="stub", solvers=SOLVERS, max_llm_attempts=2)
    step = p.next_step(_state())
    assert step.flagged_kind == "preference_fork"
    assert step.command == ["python3", "code/run_solver.py", "--workspace", ".",
                            "--iters", "200", "--tv-weight", "0.01"]

def test_invalid_selection_falls_back():
    fb = FallbackSpy()
    p = LLMImagingPlanner(_stub("nonexistent"), model="stub", solvers=SOLVERS, fallback=fb, max_llm_attempts=1)
    step = p.next_step(_state())
    assert fb.next_called == 1 and step.summary == "GAP-TV fallback"

def test_empty_recall_falls_back_immediately():
    fb = FallbackSpy()
    p = LLMImagingPlanner(_stub("best_quality"), model="stub", solvers=[], fallback=fb)
    assert p.next_step(_state()).summary == "GAP-TV fallback"

def test_replan_counts_attempts_then_falls_back():
    fb = FallbackSpy()
    p = LLMImagingPlanner(_stub("traditional_cpu"), model="stub", solvers=SOLVERS, fallback=fb, max_llm_attempts=1)
    p.next_step(_state())                                   # attempt 0 -> LLM step
    p.replan(_state(), Verdict(complete=False, repairable=True))  # -> _attempts=1
    assert p.next_step(_state()).summary == "GAP-TV fallback"
