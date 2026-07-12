from __future__ import annotations
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.imaging.planner import ReferenceImagingPlanner
from .recall import recall_cpu_cassi_solvers
from .prompt import build_selection_messages
from .extract import extract_solver_key

def _residual_from_verdict(verdict):
    try:
        ev = getattr(verdict, "evidence", {}) or {}
        return ev["report"]["s4_checks"]["forward_residual"]["evidence"]["residual"]
    except Exception:
        return None

class LLMImagingPlanner:
    """Recalls the CPU CASSI solver menu from algorithm_base, asks an LLM to select one, and runs the
    vendored GAP-TV with the recalled config; on repeated failure it delegates to a deterministic
    fallback (GAP-TV) so the agent always delivers."""
    def __init__(self, adapter, model: str, *, fallback=None, max_llm_attempts: int = 2,
                 reasoning: str = "medium", solvers=None):
        self.adapter = adapter
        self.model = model
        self.reasoning = reasoning
        self.max_llm_attempts = max_llm_attempts
        self._fallback = fallback if fallback is not None else ReferenceImagingPlanner()
        self._solvers = solvers if solvers is not None else recall_cpu_cassi_solvers()
        self._by_key = {s["key"]: s for s in self._solvers}
        self._attempts = 0
        self._in_fallback = False
        self._last_residual = None

    def _select(self, state) -> str | None:
        try:
            messages = build_selection_messages(state, self._solvers, last_residual=self._last_residual)
            parts = []
            for ev in self.adapter.stream(messages, [], model=self.model, reasoning=self.reasoning):
                text = getattr(ev, "text", None)
                if text:
                    parts.append(text)
            return extract_solver_key("".join(parts), self._by_key.keys())
        except Exception:
            return None

    def next_step(self, state) -> PlanStep:
        while not self._in_fallback and self._solvers and self._attempts < self.max_llm_attempts:
            key = self._select(state)
            if key and key in self._by_key:
                cfg = self._by_key[key]["cfg"]
                return PlanStep(
                    summary=f"reconstruct with recalled solver '{key}' "
                            f"(iters={cfg['iters']}, lam={cfg['lam']})",
                    command=["python3", "code/run_solver.py", "--workspace", ".",
                             "--iters", str(cfg["iters"]), "--tv-weight", str(cfg["lam"])],
                    flagged_kind="preference_fork",
                )
            self._attempts += 1
        self._in_fallback = True
        return self._fallback.next_step(state)

    def replan(self, state, verdict) -> None:
        if self._in_fallback:
            self._fallback.replan(state, verdict)
        else:
            r = _residual_from_verdict(verdict)
            if r is not None:
                self._last_residual = r
            self._attempts += 1
