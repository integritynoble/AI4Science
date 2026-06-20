"""Science-router agent tools (science-tier): resolve a problem to the PWM
registry and return the existing answer + physicsworldmodel.org link, or signal
contribute-to-earn; plus the registry-as-standard gate. Read-only lookups."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List, Optional

from ai4science.harness.tools.base import Tool
from ai4science.harness import registry_router

# Read-only discovery tools — free under the earn-first model.
TOOL_PRICES: dict = {"pwm_solve": 0.0, "pwm_standard_check": 0.0, "pwm_lineage": 0.0}


def _solve(workspace: str, query: str = "") -> str:
    try:
        return json.dumps(registry_router.find_problem(query))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _standard_check(workspace: str, benchmark_id: str = "", value: float = 0.0,
                    metric_field: str = "psnr_db", higher_is_better: bool = True,
                    tol: float = 0.0) -> str:
    try:
        return json.dumps(registry_router.standard_check(
            benchmark_id, float(value), metric_field=metric_field,
            higher_is_better=bool(higher_is_better), tol=float(tol)))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _lineage(workspace: str, artifact_id: str = "") -> str:
    try:
        return json.dumps({"artifact_id": artifact_id,
                           "lineage": registry_router.resolve_lineage(artifact_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def science_router_tools(gate_provider: Optional[Callable] = None,
                         workspace: Optional[Path] = None) -> List[Tool]:
    """Build the science-router tool bundle. Read-only (no PWM charge)."""
    return [
        Tool(name="pwm_solve",
             description="Resolve a science problem against physicsworldmodel.org. "
                         "If a solved benchmark answers it, returns the answer + the "
                         "artifact link (and its L1->L2->L3 lineage). If not, returns "
                         "exists=false with a contribute-to-earn hint (contributing a "
                         "new principle/twin/benchmark/solution earns PWM). Use this "
                         "FIRST for any science question.",
             parameters={"type": "object", "properties": {
                 "query": {"type": "string", "description": "the science problem / question"}},
                 "required": ["query"]},
             func=_solve, mutating=False),
        Tool(name="pwm_standard_check",
             description="Registry-as-standard gate: check whether a candidate result "
                         "meets-or-beats the leaderboard best for a benchmark. Returns "
                         "meets_or_beats, leaderboard_best, delta, reward_eligible, and "
                         "a note (below-standard results are still valid to report to "
                         "the user, just not reward-eligible).",
             parameters={"type": "object", "properties": {
                 "benchmark_id": {"type": "string"},
                 "value": {"type": "number", "description": "your result's metric value"},
                 "metric_field": {"type": "string", "default": "psnr_db"},
                 "higher_is_better": {"type": "boolean", "default": True},
                 "tol": {"type": "number", "default": 0.0}},
                 "required": ["benchmark_id", "value"]},
             func=_standard_check, mutating=False),
        Tool(name="pwm_lineage",
             description="Return the L1->L2->L3 registry lineage (principle -> digital "
                         "twin -> benchmark) for an artifact id, each with its "
                         "physicsworldmodel.org link.",
             parameters={"type": "object", "properties": {
                 "artifact_id": {"type": "string"}},
                 "required": ["artifact_id"]},
             func=_lineage, mutating=False),
    ]
