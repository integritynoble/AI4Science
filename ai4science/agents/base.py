"""Base agent interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class AgentResult:
    """The single return type from BaseAgent.run_task."""
    status: str            # "ok" | "error" | "not_available"
    message: str
    changed_files: List[Path] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Abstract agent provider.

    Sandboxing rule (enforced by callers, not the provider):
      - Agent workers may edit ONLY the current contribution workspace.
      - Agents MUST NOT modify hidden_tests/, judge/, locked benchmark
        files, or any parent PWM folders.
      - Callers must show changed files before accepting modifications.
      - The final scientific decision is NEVER made by the LLM.
    """

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True iff this provider can actually run (creds/binary present)."""
        ...

    @abstractmethod
    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        """Execute *prompt* with the given workspace + context files.

        v0.1: NoneAgent always returns ok-with-instructions; ClaudeAgent /
        CodexAgent return ``not_available`` unless their respective creds /
        binaries are detected, in which case they still defer to Phase A2.
        """
        ...
