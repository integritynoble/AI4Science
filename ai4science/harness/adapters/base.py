from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, List

from ai4science.harness.events import Message, ToolSpec


class AgentAdapter(ABC):
    backend: str = "base"

    @abstractmethod
    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        """Yield exactly one ResponseMeta per provider request, before any
        TextDelta, ToolCall, Usage, Done, or other semantic event. Provider
        observations in ResponseMeta must come only from response data and stay
        None when unavailable; adapters must not copy requested values into them.

        An all-None ResponseMeta means UNPROVEN, never "a provider was
        contacted": "no credential, nothing sent", "the stream closed empty",
        and "the provider omitted metadata" all produce the identical event. A
        guard may therefore read the PRESENCE of a ResponseMeta only as "the
        adapter reached its sequencing point", and must decide proven-vs-held on
        the observed fields alone.
        """
        raise NotImplementedError
