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
        """Available iff the `codex` CLI is on PATH.

        Like ClaudeAgent, auth is handled by the underlying CLI:

          1. API key:        export OPENAI_API_KEY=...
          2. Subscription:   run `codex login` to use a ChatGPT Plus/Pro/Team account.
        """
        return shutil.which("codex") is not None

    def unavailable_reason(self) -> str:
        reasons: List[str] = []
        if shutil.which("codex") is None:
            reasons.append("`codex` CLI binary not on PATH "
                           "(install from https://github.com/openai/codex)")
        if shutil.which("codex") is not None and not os.environ.get("OPENAI_API_KEY"):
            reasons.append("note: OPENAI_API_KEY is unset — that's fine if you "
                           "ran `codex login` (ChatGPT subscription auth).")
        return "; ".join(reasons) if reasons else "available"

    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        if not self.is_available():
            return AgentResult(
                status="not_available",
                message=(f"CodexAgent is not available: {self.unavailable_reason()}. "
                         "Set OPENAI_API_KEY and install the Codex CLI "
                         "(https://github.com/openai/codex), then re-run."),
            )
        # TODO Phase A2.5: Codex CLI subprocess wiring (AI Overseer role).
        # The Codex CLI shape is `codex exec --prompt ...` with stdin context.
        return AgentResult(
            status="not_available",
            message=(
                "CodexAgent v0.2 stub: detected codex CLI + OPENAI_API_KEY but the "
                "subprocess wiring is intentionally deferred to Phase A2.5 — "
                "Codex is the AI OVERSEER role, not the contributor. For drafting, "
                "use --agent claude. For verifying, use the deterministic Physics "
                "Judge: `ai4science overseer review --submission .`."
            ),
        )
