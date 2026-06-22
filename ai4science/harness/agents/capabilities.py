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
    from ai4science.harness.pwm_gate import PwmGate
    return list(paper_tools(brand_provider=ctx.brand_provider,
                            research_tools_provider=research_tools,
                            gate_provider=PwmGate.from_env))


def _computational_imaging(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.cassi_tools import cassi_tools
    return list(cassi_tools())


def _compute_providers(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.compute_tools import compute_tools
    return list(compute_tools())


def _ci_algorithms(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.algorithm_tools import algorithm_tools
    return list(algorithm_tools())


def _optics_design(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.optics_tools import optics_tools
    from ai4science.harness.pwm_gate import PwmGate
    return list(optics_tools(gate_provider=PwmGate.from_env,
                             workspace=ctx.workspace))


def _forward_model(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.forward_model_tools import forward_model_tools
    from ai4science.harness.pwm_gate import PwmGate
    return list(forward_model_tools(gate_provider=PwmGate.from_env,
                                    workspace=ctx.workspace))


def _science_router(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.registry_router_tools import science_router_tools
    return list(science_router_tools(gate_provider=None, workspace=ctx.workspace))


def _drug_design(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.drug_design_tools import drug_design_tools
    return list(drug_design_tools())


def _cancer(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.cancer_tools import cancer_tools
    return list(cancer_tools())


# name -> provider(ctx) -> list[Tool]. Built-in bundles.
BUILTIN_BUNDLES: Dict[str, Callable[[BuildContext], List[Tool]]] = {
    "pwm-actions": _pwm_actions,
    "pwm-data": _pwm_data,
    "onboarding": _onboarding,
    "paper-review": _paper_review,
    "computational-imaging": _computational_imaging,
    "compute-providers": _compute_providers,
    "ci-algorithms": _ci_algorithms,
    "optics-design": _optics_design,
    "forward-model": _forward_model,
    "science-router": _science_router,
    "drug-design": _drug_design,
    "cancer": _cancer,
}

# Dynamic bundles registered by tool plug-ins (manifest kind="tool"). Kept apart
# from BUILTIN_BUNDLES so a registry reload can clear/rebuild them without
# touching the built-ins.
PLUGIN_BUNDLES: Dict[str, Callable[[BuildContext], List[Tool]]] = {}

# Back-compat name: the union view used for validation + lookup.
CAPABILITY_BUNDLES: Dict[str, Callable[[BuildContext], List[Tool]]] = dict(BUILTIN_BUNDLES)


def _rebuild_union() -> None:
    CAPABILITY_BUNDLES.clear()
    CAPABILITY_BUNDLES.update(BUILTIN_BUNDLES)
    CAPABILITY_BUNDLES.update(PLUGIN_BUNDLES)


def register_plugin_bundle(name: str, provider: Callable[[BuildContext], List[Tool]]) -> None:
    """Register a tool plug-in as a capability bundle any agent can reference."""
    PLUGIN_BUNDLES[name] = provider
    _rebuild_union()


def clear_plugin_bundles() -> None:
    PLUGIN_BUNDLES.clear()
    _rebuild_union()


def resolve_capability(name: str, ctx: BuildContext) -> List[Tool]:
    try:
        provider = CAPABILITY_BUNDLES[name]
    except KeyError:
        valid = ", ".join(sorted(CAPABILITY_BUNDLES))
        raise ValueError(f"unknown capability bundle {name!r}; valid: {valid}")
    return provider(ctx)
