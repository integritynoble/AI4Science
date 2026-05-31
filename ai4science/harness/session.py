from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from ai4science.harness.events import Message, Usage
from ai4science.harness.loop import run_loop
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools import default_registry
from ai4science.harness.tools.base import Registry


class AgentSession:
    """A live, brand-swappable conversation. History is brand-neutral."""

    def __init__(self, *, adapter, model: str, backend: str, workspace: Path,
                 registry: Optional[Registry] = None,
                 read_only: bool = False, auto_yes: bool = False,
                 reasoning: str = "high",
                 confirm: Optional[Callable[[str, dict, str], bool]] = None,
                 on_text: Callable[[str], None] = lambda t: None,
                 meter: Callable[[Usage], None] = lambda u: None,
                 compact_limit_chars: int = 0,
                 summarize: Optional[Callable[[str], str]] = None) -> None:
        self.adapter = adapter
        self.model = model
        self.backend = backend
        self.workspace = workspace
        self.registry = registry or default_registry()
        self.reasoning = reasoning
        self.on_text = on_text
        self.meter = meter
        self.history: List[Message] = []
        self.gate = PermissionGate(workspace=workspace, read_only=read_only,
                                   auto_yes=auto_yes, confirm=confirm)
        self.compact_limit_chars = compact_limit_chars
        self.summarize = summarize

    def set_brand(self, adapter, model: str, backend: str) -> None:
        """Swap the brand mid-session; history is preserved (brand-neutral)."""
        self.adapter, self.model, self.backend = adapter, model, backend

    def run_turn(self, user_input: str, images=None) -> str:
        if self.summarize and self.compact_limit_chars:
            from ai4science.harness.compaction import maybe_compact
            self.history, _ = maybe_compact(
                self.history, limit_chars=self.compact_limit_chars,
                summarize=self.summarize)
        self.history.append(Message(role="user", content=user_input, images=list(images or [])))
        return run_loop(
            adapter=self.adapter, model=self.model, reasoning=self.reasoning,
            history=self.history, workspace=self.workspace, registry=self.registry,
            gate=self.gate, on_text=self.on_text, meter=self.meter,
        )
