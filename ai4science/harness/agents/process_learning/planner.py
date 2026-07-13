from __future__ import annotations
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.work.planner import DEFAULT_MODEL, MAX_LLM_TOKENS, llm_text
from .extract import parse_work_action
from .prompt import build_process_messages


class LLMProcessPlanner:
    """Freeform brokered trace-explanation planner (mirror of LLMResearchPlanner).
    Reads the staged trace via sandbox commands and writes explanation.md; delivery
    is gated by the CP-side grounding verifier (reused research_check). No fallback:
    unusable output -> honest blocker."""

    def __init__(self, client, run_id: str, *, run_label: str, coverage_points: list,
                 trace_index: list, model: str = DEFAULT_MODEL,
                 max_parse_retries: int = 2, prompt_profile: str = "terse"):
        self.client = client
        self.run_id = run_id
        self.model = model
        self.run_label = run_label
        self.coverage_points = list(coverage_points)
        self.trace_index = list(trace_index)
        self._max_parse_retries = max_parse_retries
        self._last_feedback = None
        self._prompt_profile = prompt_profile

    def _call(self, state):
        system, messages = build_process_messages(
            state, self.run_label, self.coverage_points, self.trace_index,
            last_feedback=self._last_feedback, prompt_profile=self._prompt_profile)
        resp = self.client.llm_egress(self.run_id, {
            "model": self.model, "max_tokens": MAX_LLM_TOKENS,
            "system": system, "messages": messages})
        return parse_work_action(llm_text(resp))

    def next_step(self, state) -> PlanStep:
        for _ in range(self._max_parse_retries + 1):
            action = self._call(state)
            if action is None:
                continue
            if action.action == "step":
                return PlanStep(summary=action.summary, command=action.command,
                                stage_files=action.stage_files, request_verify=False)
            if action.action == "verify":
                return PlanStep(summary="verify trace grounding", command=[], request_verify=True)
            if action.action == "blocked":
                return PlanStep(summary=f"blocked: {action.reason}", command=[], done=True)
        return PlanStep(summary="planner output unusable", command=[], done=True)

    def replan(self, state, verdict) -> None:
        ev = getattr(verdict, "evidence", {}) or {}
        self._last_feedback = ev.get("feedback")
