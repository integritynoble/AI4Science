from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, List

from ai4science.harness.events import Message, ToolSpec


class AgentAdapter(ABC):
    backend: str = "base"

    @abstractmethod
    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        """Yield TextDelta / ToolCall / Usage / Done events for one turn."""
        raise NotImplementedError
