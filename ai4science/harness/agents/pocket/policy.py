"""The tunable tool-selection policy — the Pocket agent's RSI harness knob.

`run_pocket` already accepts a `select=` hook. A `KeywordPolicy` is a *data-backed*
implementation of that hook: a `{tool_name: (phrase, …)}` map the RSI loop learns
from labeled examples. The policy iterates the *registry* (so tool identity and
order stay owned by `tools.py`) and is the ONLY thing the loop mutates — it sits
DOWNSTREAM of run_pocket's risk-ceiling gate, so no learned policy can weaken
safety (a consequential intent hands off before selection is ever reached).
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from ai4science.harness.agents.pocket.tools import Tool, default_registry


class KeywordPolicy:
    def __init__(self, keyword_map: Dict[str, Tuple[str, ...]]):
        # de-dup phrases per tool while preserving order.
        self.keyword_map: Dict[str, Tuple[str, ...]] = {
            k: tuple(dict.fromkeys(v)) for k, v in keyword_map.items()
        }

    def select(self, intent: str, registry: Sequence[Tool]) -> Optional[Tool]:
        low = (intent or "").lower()
        for tool in registry:
            kws = self.keyword_map.get(tool.name, ())
            if kws and any(kw in low for kw in kws):
                return tool
        return None

    def with_added(self, tool_name: str, phrases: Sequence[str]) -> "KeywordPolicy":
        """Return a NEW policy with `phrases` added to `tool_name` (immutable)."""
        new = {k: tuple(v) for k, v in self.keyword_map.items()}
        new[tool_name] = tuple(dict.fromkeys(new.get(tool_name, ()) + tuple(phrases)))
        return KeywordPolicy(new)

    def added_since(self, base: "KeywordPolicy") -> Dict[str, Tuple[str, ...]]:
        """The phrases this policy has that `base` does not — the learned diff."""
        diff: Dict[str, Tuple[str, ...]] = {}
        for name, kws in self.keyword_map.items():
            base_kws = set(base.keyword_map.get(name, ()))
            extra = tuple(k for k in kws if k not in base_kws)
            if extra:
                diff[name] = extra
        return diff

    def as_map(self) -> Dict[str, Tuple[str, ...]]:
        return {k: tuple(v) for k, v in self.keyword_map.items()}


def incumbent_policy() -> KeywordPolicy:
    """The shipped baseline: exactly today's default_registry() keywords, so the
    RSI incumbent == the live agent's current behavior."""
    return KeywordPolicy({t.name: t.match for t in default_registry()})
