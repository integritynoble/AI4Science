from __future__ import annotations

from typing import Callable, Dict, List

from ai4science.harness.tools.base import Tool
from ai4science.harness.agents.context import BuildContext


def _pwm_actions(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness import mcp_pwm
    return list(mcp_pwm.pwm_tools())


def _pwm_data(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.research_tools import research_tools
    return list(research_tools())


# name -> provider(ctx) -> list[Tool]. The "paper-review" bundle is registered by
# the paper-mode plan (its paper_tools module does not exist yet).
CAPABILITY_BUNDLES: Dict[str, Callable[[BuildContext], List[Tool]]] = {
    "pwm-actions": _pwm_actions,
    "pwm-data": _pwm_data,
}


def resolve_capability(name: str, ctx: BuildContext) -> List[Tool]:
    try:
        provider = CAPABILITY_BUNDLES[name]
    except KeyError:
        valid = ", ".join(sorted(CAPABILITY_BUNDLES))
        raise ValueError(f"unknown capability bundle {name!r}; valid: {valid}")
    return provider(ctx)
