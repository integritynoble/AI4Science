"""Agent → LLM routing with fallback (design point 10).

Different agents prefer different LLMs, and fall through to another when the
preferred one isn't available on this host:

  orchestration → Opus 4.7   (heavy reasoning / planning)
  checking      → GPT-5.5     (independent second opinion / review)
  fast          → Gemini 3.5 Flash (quick, cheap turns)

Each agent has an ordered chain of (backend, model) candidates; routing picks
the first whose backend is reachable here. The chosen LLM also resolves to the
wallet provider that serves that backend (so usage accrues to the right
wallet). Point 11 (user keys > wallet providers) is layered on top via the
`prefer` argument.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Tuple

# Agent → ordered fallback chain of (backend, model).
AGENT_CHAINS: Dict[str, List[Tuple[str, str]]] = {
    "orchestration": [
        ("anthropic", "claude-opus-4-8"),     # verified live on the subscription
        ("anthropic", "claude-opus-4-7"),
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-5.5"),
        ("gemini", "gemini-3.1-pro-preview"),
    ],
    "checking": [
        ("openai", "gpt-5.5"),
        ("anthropic", "claude-opus-4-8"),
        ("gemini", "gemini-3.1-pro-preview"),   # 'gemini-3.1-pro' (plain) 404s
        ("deepseek", "deepseek-ai/deepseek-r1-0528-maas"),   # reasoning, via Vertex
    ],
    "fast": [
        ("gemini", "gemini-3.5-flash"),
        ("anthropic", "claude-haiku-4-5"),
        ("openai", "gpt-5.5-nano"),     # nano = fast/cheap (not the heavy gpt-5.5)
        ("qwen", "qwen/qwen3-235b-a22b-instruct-2507-maas"),  # via Vertex
    ],
}

# Per-agent reasoning effort, applied when the chosen LLM supports it (codex
# `model_reasoning_effort`, Anthropic extended thinking). Checking reviews
# carefully → high; fast favors speed → low.
AGENT_REASONING: Dict[str, str] = {
    "orchestration": "high",
    "checking": "high",
    "fast": "low",
}


def backend_available(backend: str) -> bool:
    """Is this LLM backend reachable on this host right now?"""
    try:
        if backend == "anthropic":
            from ai4science.agents import ClaudeAgent
            return ClaudeAgent().is_available()
        if backend == "openai":
            from ai4science.agents import get_agent
            return get_agent("codex").is_available()
        if backend == "gemini":
            from ai4science.llm import gemini
            return gemini.is_available()
        if backend in ("deepseek", "qwen"):
            from ai4science.llm import openai_compat
            return openai_compat.is_available(backend)
    except Exception:
        return False
    return False


def _provider_for(backend: str):
    """The wallet provider serving this backend (first active), or None."""
    from ai4science.llm.registry import providers_for_backend
    provs = providers_for_backend(backend)
    return provs[0] if provs else None


def _select_source(backend: str):
    """Pick the credential source for a backend, honoring user preference (#11).

    Returns (source, provider_id, wallet, price_multiplier):
      source 'user'   → the user's own login/key; no wallet, 0 PWM (billed to
                        the user's own account).
      source 'wallet' → a wallet-bound provider; usage priced in PWM.

    Preference (user config): 'user' (own first — default), 'wallet' (wallet
    first), or a specific provider_id.
    """
    from ai4science import user
    from ai4science.llm.registry import get_provider as get_llm_provider

    pref = user.preference()
    wallet_prov = _provider_for(backend)
    user_ok = user.has_own_for(backend)

    def _wallet(p):
        return ("wallet", p.provider_id, p.wallet_address, p.price_multiplier)
    user_tuple = ("user", None, None, 0.0)

    # A specific wallet provider was pinned.
    if pref not in ("user", "wallet"):
        p = get_llm_provider(pref)
        if p is not None and p.backend == backend and p.status == "active":
            return _wallet(p)
        # pinned provider doesn't serve this backend → fall through to user-first

    if pref == "wallet":
        if wallet_prov is not None:
            return _wallet(wallet_prov)
        if user_ok:
            return user_tuple
    else:  # 'user' (default) or an unmatched pin
        if user_ok:
            return user_tuple
        if wallet_prov is not None:
            return _wallet(wallet_prov)

    # Last resort.
    return _wallet(wallet_prov) if wallet_prov is not None else user_tuple


class Route(NamedTuple):
    agent: str
    backend: str
    model: str
    reasoning: str             # reasoning effort: high | medium | low
    provider_id: Optional[str]
    wallet: Optional[str]
    is_fallback: bool          # True if not the agent's first choice
    price_multiplier: float = 1.0   # provider's fraction of official price
    source: str = "wallet"     # 'user' (own login/key, 0 PWM) | 'wallet'


def resolve(agent: str) -> Optional[Route]:
    """Resolve an agent to the first reachable LLM in its fallback chain, and
    pick the credential source (user vs wallet) per preference (#11).

    Returns None if the agent is unknown or no candidate backend is reachable.
    """
    chain = AGENT_CHAINS.get(agent)
    if not chain:
        return None
    for i, (backend, model) in enumerate(chain):
        if backend_available(backend):
            source, provider_id, wallet, mult = _select_source(backend)
            return Route(
                agent=agent, backend=backend, model=model,
                reasoning=AGENT_REASONING.get(agent, "medium"),
                provider_id=provider_id, wallet=wallet,
                is_fallback=(i > 0), price_multiplier=mult, source=source,
            )
    return None


def resolve_all() -> Dict[str, Optional[Route]]:
    return {agent: resolve(agent) for agent in AGENT_CHAINS}
