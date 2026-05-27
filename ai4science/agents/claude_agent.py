"""ClaudeAgent — Phase A2 stub. Wires up to the Claude Agent SDK.

v0.1 contract:
  - is_available() checks ANTHROPIC_API_KEY in the environment AND
    whether claude-agent-sdk is importable.
  - run_task() returns 'not_available' with the migration message until
    Phase A2 wires this to the real SDK.

Phase A2 (when wiring):
  1. pip install claude-agent-sdk
  2. Build system prompt = PWM_AI4SCIENCE.md system context +
     a structured-extraction instruction (see pwm_nonprofit's
     routers/ai4science.py for the template).
  3. Call agent.run(prompt, context_files=[...]) with a tight token budget.
  4. Persist the response. NEVER allow the agent to issue a verdict; the
     verdict belongs to the deterministic Physics Judge.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from ai4science.agents.base import AgentResult, BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"

    def is_available(self) -> bool:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import claude_agent_sdk  # noqa: F401
        except Exception:
            return False
        return True

    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        if not self.is_available():
            return AgentResult(
                status="not_available",
                message=(
                    "ClaudeAgent is not available. Set ANTHROPIC_API_KEY and "
                    "`pip install claude-agent-sdk`, then re-run."
                ),
            )
        # TODO Phase A2: real SDK call.
        return AgentResult(
            status="not_available",
            message=(
                "ClaudeAgent v0.1 stub. Phase A2 wires up claude-agent-sdk. "
                "For now, please draft your artifact manually using the "
                "ai4science contribute <type> templates."
            ),
        )
