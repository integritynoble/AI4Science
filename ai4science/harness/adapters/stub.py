from __future__ import annotations

from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.events import Message, ToolSpec


class StubAdapter(AgentAdapter):
    backend = "stub"

    def __init__(self, script: List[List[object]]) -> None:
        self._script = list(script)
        self._i = 0

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        turn = self._script[min(self._i, len(self._script) - 1)]
        self._i += 1
        for ev in turn:
            yield ev
