from __future__ import annotations

from typing import Callable

from ai4science.harness.adapters.anthropic import AnthropicAdapter
from ai4science.harness.adapters.openai import OpenAIAdapter
from ai4science.harness.events import Usage
from ai4science.llm import ledger, pricing, routing

# openai/gemini/deepseek/qwen all speak OpenAI-compatible REST → OpenAIAdapter;
# anthropic uses the Messages API → AnthropicAdapter. (The native GeminiAdapter
# is unused: this deployment reaches Gemini via its OpenAI-compat endpoint.)


def _proxy_creds():
    """(base, token) for the backend LLM proxy if a PWM login is present and
    PWM_NO_PROXY isn't set, else None. Lets a credential-less machine serve
    turns through the founder gateway, charged in PWM."""
    import os
    if _truthy(os.environ.get("PWM_NO_PROXY")):
        return None
    token = os.environ.get("PWM_TOKEN") or os.environ.get("PWM_ONBOARD_TOKEN")
    base = os.environ.get("PWM_BASE") or os.environ.get("PWM_ONBOARD_BASE")
    if not token:
        try:
            from ai4science import pwm_account
            acct = pwm_account.load() or {}
            token, base = acct.get("token"), base or acct.get("base")
        except Exception:
            pass
    if token and base:
        return base, token
    if token:
        return "https://physicsworldmodel.org", token
    return None


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def adapter_for(backend: str):
    from ai4science.harness.adapters import creds as _creds
    # OpenAI runs via the codex/ChatGPT OAuth subscription when present — the
    # api-key path 401s in this deployment. (Responses API, not chat/completions.)
    if backend == "openai":
        from ai4science.harness.adapters import codex_creds
        if codex_creds.codex_available():
            from ai4science.harness.adapters.codex import CodexAdapter
            return CodexAdapter()
    # No local credential for this backend? Serve it through the founder gateway
    # (charged in PWM) if the user is logged in to physicsworldmodel.org.
    if not _local_available(backend):
        pc = _proxy_creds()
        if pc is not None:
            from ai4science.harness.adapters.proxy import ProxyAdapter
            return ProxyAdapter(backend=backend, base=pc[0], token=pc[1])
    c = _creds.resolve(backend)
    if c.kind == "anthropic":
        return AnthropicAdapter(creds=c)
    return OpenAIAdapter(creds=c)   # gemini/deepseek/qwen (+ openai api-key) are OpenAI-compatible


def _local_available(backend: str) -> bool:
    """True if THIS machine can serve the backend from a local credential."""
    from ai4science.harness.adapters import creds as _creds
    if backend == "openai":
        from ai4science.harness.adapters import codex_creds
        if codex_creds.codex_available():
            return True
    return _creds.available(backend)


def harness_available(backend: str) -> bool:
    # Available if served locally OR through the founder proxy (PWM login).
    return _local_available(backend) or _proxy_creds() is not None


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
