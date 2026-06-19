from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ai4science.harness import pwm_data
from ai4science.harness.tools.base import Tool

_STR = {"type": "string"}


def _wrap(fn_name: str, *, takes_arg: str | None = None):
    """Return a harness tool func that resolves pwm_data.<fn_name> at call-time.

    Using late binding (getattr) ensures monkeypatching in tests works even
    when research_tools() has already been called and the list built.
    """
    def _tool(workspace: Path, **args) -> str:
        fn = getattr(pwm_data, fn_name)
        try:
            result = fn(args[takes_arg]) if takes_arg else fn()
        except Exception as exc:
            return f"[pwm error] {exc}"
        return json.dumps(result, indent=2, default=str)[:20000]
    return _tool


def research_tools() -> List[Tool]:
    obj = {"type": "object", "properties": {}}
    id_obj = {
        "type": "object",
        "properties": {"artifact_id": _STR},
        "required": ["artifact_id"],
    }
    bench_obj = {
        "type": "object",
        "properties": {"benchmark_id": _STR},
        "required": ["benchmark_id"],
    }
    ref_obj = {
        "type": "object",
        "properties": {"ref": _STR},
        "required": ["ref"],
    }
    query_obj = {
        "type": "object",
        "properties": {"query": _STR},
        "required": ["query"],
    }
    return [
        Tool(
            "pwm_search",
            "Keyword-search the PWM registry (principles + digital-twin specs + "
            "benchmarks) by topic or domain — e.g. 'CASSI', 'denoising', 'MRI "
            "reconstruction'. Use this FIRST to ground a research question, instead "
            "of listing the whole registry.",
            query_obj,
            _wrap("search", takes_arg="query"),
            mutating=False,
        ),
        Tool(
            "pwm_principles",
            "List PWM registry principles (L1: id/title/domain).",
            obj,
            _wrap("principles"),
            mutating=False,
        ),
        Tool(
            "pwm_principle",
            "Fetch a PWM principle's full detail by artifact_id — includes its "
            "digital-twin specs and registered benchmarks.",
            id_obj,
            _wrap("principle", takes_arg="artifact_id"),
            mutating=False,
        ),
        Tool(
            "pwm_specs",
            "List PWM digital-twin specs (L2: the forward-model setups under "
            "principles — id/title/spec_type/parent principle).",
            obj,
            _wrap("specs"),
            mutating=False,
        ),
        Tool(
            "pwm_spec",
            "Fetch a digital-twin spec's full detail by artifact_id "
            "(six_tuple, protocol_fields, d_spec — the forward model).",
            id_obj,
            _wrap("spec", takes_arg="artifact_id"),
            mutating=False,
        ),
        Tool(
            "pwm_benchmarks",
            "List PWM benchmarks (id/title/chain_status).",
            obj,
            _wrap("benchmarks"),
            mutating=False,
        ),
        Tool(
            "pwm_benchmark",
            "Fetch a PWM benchmark by ref.",
            ref_obj,
            _wrap("benchmark", takes_arg="ref"),
            mutating=False,
        ),
        Tool(
            "pwm_solutions",
            "Registered SOTA solutions + scores for a benchmark "
            "(the leaderboard). Research mode can build on these.",
            bench_obj,
            _wrap("solutions", takes_arg="benchmark_id"),
            mutating=False,
        ),
        Tool(
            "pwm_overview",
            "PWM registry overview.",
            obj,
            _wrap("overview"),
            mutating=False,
        ),
    ]
