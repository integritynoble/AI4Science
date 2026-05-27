"""ai4science.agents — pluggable LLM agent providers.

v0.1 ships three providers:
  - NoneAgent    (default; prints instructions, makes no LLM call)
  - ClaudeAgent  (TODO Phase A2 wiring to Claude Agent SDK)
  - CodexAgent   (TODO Phase A2 wiring to OpenAI Codex CLI)

Hard rule (from PWM_AI_RESEARCHER_OVERSEER_SYSTEM_2026-05-27.md):
  - AI4Science (researcher role) → Anthropic family (Claude Agent SDK)
  - AI Overseer                   → OpenAI family (Codex)
  - Physics Judge                 → NO LLM at all; deterministic Python
"""
from ai4science.agents.base import BaseAgent
from ai4science.agents.none_agent import NoneAgent
from ai4science.agents.claude_agent import ClaudeAgent
from ai4science.agents.codex_agent import CodexAgent

__all__ = ["BaseAgent", "NoneAgent", "ClaudeAgent", "CodexAgent", "get_agent"]


def get_agent(name: str) -> BaseAgent:
    """Resolve a provider name to an agent instance."""
    table = {
        "none": NoneAgent,
        "claude": ClaudeAgent,
        "codex": CodexAgent,
    }
    cls = table.get(name.lower())
    if cls is None:
        raise ValueError(f"unknown agent provider: {name!r} (choose from {list(table)})")
    return cls()
