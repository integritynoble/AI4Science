"""NoneAgent — default provider; prints instructions instead of calling an LLM."""
from __future__ import annotations

from pathlib import Path
from typing import List

from ai4science.agents.base import AgentResult, BaseAgent


class NoneAgent(BaseAgent):
    name = "none"

    def is_available(self) -> bool:
        return True   # always available; no creds needed

    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        instructions = (
            f"NoneAgent received your task in {workspace}.\n\n"
            f"Prompt: {prompt!r}\n\n"
            f"Context files visible to the agent:\n"
            + "".join(f"  - {p}\n" for p in context_files)
            + "\nv0.1 does not call any LLM. To enable AI assistance:\n"
              "  - export ANTHROPIC_API_KEY=...  and use --agent claude\n"
              "  - or install OpenAI Codex CLI and use --agent codex\n"
        )
        return AgentResult(status="ok", message=instructions, suggestions=[])
