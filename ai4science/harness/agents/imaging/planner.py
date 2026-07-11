from __future__ import annotations
from ai4science.harness.runtime.pev import PlanStep

class ReferenceImagingPlanner:
    """Deterministic baseline planner: run the vendored GAP-TV reconstruction, and on a
    repairable judge failure retry with more solver iterations, up to ``max_repairs``."""
    def __init__(self, base_iters: int = 80, iter_step: int = 80, max_repairs: int = 2):
        self._iters = base_iters
        self.iter_step = iter_step
        self.max_repairs = max_repairs
        self._attempts = 0

    def next_step(self, state) -> PlanStep:
        if self._attempts > self.max_repairs:
            return PlanStep(summary="deliver", command=[], done=True)
        return PlanStep(
            summary=f"reconstruct with GAP-TV (iters={self._iters})",
            command=["python3", "code/run_solver.py", "--workspace", ".",
                     "--iters", str(self._iters), "--tv-weight", "0.01"],
            action_type="sandbox_exec",
            flagged_kind="preference_fork",
        )

    def replan(self, state, verdict) -> None:
        self._attempts += 1
        if getattr(verdict, "repairable", False):
            self._iters += self.iter_step
