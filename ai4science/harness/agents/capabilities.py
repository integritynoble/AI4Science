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


def _onboarding(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.onboard_tools import onboard_tools
    return list(onboard_tools())


def _paper_review(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.paper_tools import paper_tools
    from ai4science.harness.research_tools import research_tools
    return list(paper_tools(brand_provider=ctx.brand_provider,
                            research_tools_provider=research_tools))


def _computational_imaging(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.cassi_tools import cassi_tools
    return list(cassi_tools())


def _compute_providers(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.compute_tools import compute_tools
    return list(compute_tools())


# name -> provider(ctx) -> list[Tool].
CAPABILITY_BUNDLES: Dict[str, Callable[[BuildContext], List[Tool]]] = {
    "pwm-actions": _pwm_actions,
    "pwm-data": _pwm_data,
    "onboarding": _onboarding,
    "paper-review": _paper_review,
    "computational-imaging": _computational_imaging,
    "compute-providers": _compute_providers,
}


def resolve_capability(name: str, ctx: BuildContext) -> List[Tool]:
    try:
        provider = CAPABILITY_BUNDLES[name]
    except KeyError:
        valid = ", ".join(sorted(CAPABILITY_BUNDLES))
        raise ValueError(f"unknown capability bundle {name!r}; valid: {valid}")
    return provider(ctx)
