from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple


@dataclass(frozen=True)
class AgentSpec:
    """One pluggable agent. Discovered from agents/specs/*.py (module attr AGENT)."""
    name: str                                   # unique id, e.g. "research"
    tier: str                                   # "open" (no PWM) | "science" (PWM moat)
    category: str                               # "core" | "specific" | "hidden"
    title: str                                  # short human label
    description: str                            # one-line; shown in /mode + dispatch enum
    keywords: Tuple[str, ...] = ()              # extra search terms
    system_prompt: Optional[str] = None
    capabilities: Tuple[str, ...] = ()          # bundle names added on top of the CC base
    allow_as_subagent: bool = True
    extra_tools: Optional[Callable] = None      # ctx -> list[Tool], optional custom tools
