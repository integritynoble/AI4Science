from __future__ import annotations

from typing import Callable

from ai4science.harness.adapters.anthropic import AnthropicAdapter
from ai4science.harness.adapters.openai import OpenAIAdapter
from ai4science.harness.adapters.gemini import GeminiAdapter
from ai4science.harness.events import Usage
from ai4science.llm import ledger, pricing, routing

_ADAPTERS = {"anthropic": AnthropicAdapter, "openai": OpenAIAdapter, "gemini": GeminiAdapter}


def adapter_for(backend: str):
    cls = _ADAPTERS.get(backend)
    if cls is None:
        raise ValueError(f"no harness adapter for backend {backend!r}")
    return cls()


def make_meter(*, backend: str, model: str) -> Callable[[Usage], None]:
    def _meter(u: Usage) -> None:
        try:
            _src, _pid, wallet, mult = routing._select_source(backend)
            usage = {"input": u.input, "output": u.output, "total": u.total}
            cost = pricing.price_call(model, usage, price_multiplier=mult)
            ledger.record(agent="common-interactive", backend=backend, model=model,
                          wallet=wallet, usage=usage, cost=cost)
        except Exception:
            pass
    return _meter
