"""CodexAgent — Phase A2 stub. Wires up to OpenAI Codex CLI.

v0.1 contract:
  - is_available() checks OPENAI_API_KEY and whether `codex` is on PATH.
  - run_task() returns 'not_available' with the migration message until
    Phase A2 wires this to the real CLI.

CodexAgent is intended for the AI Overseer role (different LLM family
than ClaudeAgent), per the oversight architecture hard rule.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

from ai4science.agents.base import AgentResult, BaseAgent


class CodexAgent(BaseAgent):
    name = "codex"

    def is_available(self) -> bool:
        if not os.environ.get("OPENAI_API_KEY"):
            return False
        if shutil.which("codex") is None:
            return False
        return True

    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        if not self.is_available():
            return AgentResult(
                status="not_available",
                message=(
                    "CodexAgent is not available. Set OPENAI_API_KEY and install "
                    "the Codex CLI (https://github.com/openai/codex), then re-run."
                ),
            )
        # TODO Phase A2: subprocess call to `codex --prompt ... --context ...`
        return AgentResult(
            status="not_available",
            message=(
                "CodexAgent v0.1 stub. Phase A2 wires up the OpenAI Codex CLI "
                "for the AI Overseer role. For now, please draft your artifact "
                "manually using the ai4science contribute <type> templates."
            ),
        )
