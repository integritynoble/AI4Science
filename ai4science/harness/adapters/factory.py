from __future__ import annotations

from typing import Callable

from ai4science.harness.adapters.anthropic import AnthropicAdapter
from ai4science.harness.adapters.openai import OpenAIAdapter
from ai4science.harness.events import Usage
from ai4science.llm import ledger, pricing, routing

# openai/gemini/deepseek/qwen all speak OpenAI-compatible REST → OpenAIAdapter;
# anthropic uses the Messages API → AnthropicAdapter. (The native GeminiAdapter
# is unused: this deployment reaches Gemini via its OpenAI-compat endpoint.)


def adapter_for(backend: str):
    from ai4science.harness.adapters import creds as _creds
    # OpenAI runs via the codex/ChatGPT OAuth subscription when present — the
    # api-key path 401s in this deployment. (Responses API, not chat/completions.)
    if backend == "openai":
        from ai4science.harness.adapters import codex_creds
        if codex_creds.codex_available():
            from ai4science.harness.adapters.codex import CodexAdapter
            return CodexAdapter()
    c = _creds.resolve(backend)
    if c.kind == "anthropic":
        return AnthropicAdapter(creds=c)
    return OpenAIAdapter(creds=c)   # gemini/deepseek/qwen (+ openai api-key) are OpenAI-compatible


def harness_available(backend: str) -> bool:
    from ai4science.harness.adapters import creds as _creds
    if backend == "openai":
        from ai4science.harness.adapters import codex_creds
        if codex_creds.codex_available():
            return True
    return _creds.available(backend)


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
