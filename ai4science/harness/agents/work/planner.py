from __future__ import annotations
from ai4science.harness.runtime.pev import PlanStep
from .extract import parse_work_action
from .prompt import build_work_messages

DEFAULT_MODEL = "claude-sonnet-5"
MAX_LLM_TOKENS = 4096


def llm_text(resp: dict) -> str:
    """Concatenated text blocks of a brokered /llm_egress Messages response."""
    if not resp.get("ok"):
        return ""
    content = (resp.get("response") or {}).get("content") or []
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


class LLMWorkPlanner:
    """Freeform brokered planner. Every LLM call goes through the control
    plane's /llm_egress (no agent-side key, governor-metered); every authored
    step runs in the A1 sandbox; delivery is gated by the CP-side command
    judge. There is no deterministic fallback for general work: repeated
    unusable LLM output produces an honest blocker, never a fabricated step."""

    def __init__(self, client, run_id: str, *, criteria: dict,
                 model: str = DEFAULT_MODEL, max_parse_retries: int = 2,
                 prompt_profile: str = "terse"):
        self.client = client
        self.run_id = run_id
        self.model = model
        self._criteria = criteria
        self._max_parse_retries = max_parse_retries
        self._last_feedback = None
        self._prompt_profile = prompt_profile

    def _call(self, state):
        system, messages = build_work_messages(state, self._criteria,
                                               last_feedback=self._last_feedback,
                                               prompt_profile=self._prompt_profile)
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
                return PlanStep(summary="verify success criteria", command=[],
                                request_verify=True)
            if action.action == "blocked":
                return PlanStep(summary=f"blocked: {action.reason}", command=[], done=True)
            # propose_criteria mid-run: criteria are write-once -> unusable output
        return PlanStep(summary="planner output unusable", command=[], done=True)

    def replan(self, state, verdict) -> None:
        ev = getattr(verdict, "evidence", {}) or {}
        self._last_feedback = ev.get("feedback")
