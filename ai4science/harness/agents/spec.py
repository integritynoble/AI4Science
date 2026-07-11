from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


@dataclass(frozen=True)
class AgentSpec:
    """One pluggable agent. Discovered from agents/specs/*.py (module attr AGENT)
    or from a plug-in manifest in the plugins dir (see agents/plugins.py)."""
    name: str                                   # unique id, e.g. "research"
    tier: str                                   # "open" (no PWM) | "science" (PWM moat)
    category: str                               # "core" | "specific" | "hidden"
    title: str                                  # short human label
    description: str                            # one-line; shown in /agent + dispatch enum
    keywords: Tuple[str, ...] = ()              # extra search terms
    system_prompt: Optional[str] = None
    capabilities: Tuple[str, ...] = ()          # bundle names added on top of the CC base
    allow_as_subagent: bool = True
    extra_tools: Optional[Callable] = None      # ctx -> list[Tool], optional custom tools
    aliases: Tuple[str, ...] = ()               # old/alt names that resolve to this spec
    default_backend: Optional[str] = None       # preferred LLM backend when user gives none
    order: int = 100                            # display order in the /agent menu (lower first)
    # Plug-and-play extensions (manifest plug-ins; builtin specs leave these empty):
    wallet: Optional[str] = None                # PWM address that charges for using this agent
    price_pwm: float = 0.0                      # per-use price set by the contributor (0 = free)
    mcp_servers: Tuple[Dict[str, Any], ...] = ()  # external MCP servers providing this agent's tools
    source: str = "builtin"                     # "builtin" | "plugin" (provenance)
    # Interaction profiles (for agent mode/interaction specialization):
    supported_profiles: Tuple[str, ...] = ("I0", "I1", "I2")  # list of profile IDs this agent supports
    default_profile: str = "I1"                 # default interaction profile when user gives none
    approval_required_for: Tuple[str, ...] = ()  # operations ("publish", "deploy", "spend") requiring approval
