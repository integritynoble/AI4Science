from __future__ import annotations
from ai4science.harness.runtime.pev import PlanStep

class ReferenceImagingPlanner:
    """Deterministic baseline planner: run the vendored GAP-TV reconstruction, and on a
    repairable judge failure retry with more solver iterations, up to ``max_repairs``."""
    def __init__(self, base_iters: int = 300, iter_step: int = 80, max_repairs: int = 2,
                 tv_weight: float = 0.001):
        # 300 / 0.001 is the discrepancy-principle point on the real CAVE
        # scenes: it drives the forward residual to ~0.0025 against a 0.003
        # noise floor, which is what `noise_consistency` asks for, and lands
        # within 0.1 dB of the best PSNR anywhere in the sweep. The old
        # 80 / 0.01 came from the synthetic fixture; on real scenes it
        # over-smooths (residual 0.019, judge fail) and 150 iterations is not
        # enough to converge on the harder scenes.
        self._iters = base_iters
        self.iter_step = iter_step
        self.max_repairs = max_repairs
        self._tv_weight = tv_weight
        self._attempts = 0

    def next_step(self, state) -> PlanStep:
        if self._attempts > self.max_repairs:
            return PlanStep(summary="deliver", command=[], done=True)
        return PlanStep(
            summary=f"reconstruct with GAP-TV (iters={self._iters})",
            command=["python3", "code/run_solver.py", "--workspace", ".",
                     "--iters", str(self._iters), "--tv-weight", str(self._tv_weight)],
            action_type="sandbox_exec",
            flagged_kind="preference_fork",
        )

    def replan(self, state, verdict) -> None:
        self._attempts += 1
        if getattr(verdict, "repairable", False):
            self._iters += self.iter_step
