from __future__ import annotations

import os
from typing import Dict, List

from ai4science.harness import transport

DEFAULT_BASE = "https://explorer.physicsworldmodel.org/api"


def base() -> str:
    return os.environ.get("PWM_EXPLORER_BASE", DEFAULT_BASE).rstrip("/")


def _items(d, *keys) -> List[Dict]:
    if isinstance(d, list):
        return d
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return v
    return []


def principles() -> List[Dict]:
    return _items(transport.get_json(f"{base()}/principles"), "genesis", "principles")


def principle(artifact_id: str) -> Dict:
    d = transport.get_json(f"{base()}/principles/{artifact_id}")
    return d.get("principle", d) if isinstance(d, dict) else d


def benchmarks() -> List[Dict]:
    return _items(transport.get_json(f"{base()}/benchmarks"), "genesis", "benchmarks")


def benchmark(ref: str) -> Dict:
    d = transport.get_json(f"{base()}/benchmarks/{ref}")
    return d.get("benchmark", d) if isinstance(d, dict) else d


def solutions(benchmark_id: str) -> List[Dict]:
    """Registered solutions/baselines + scores for a benchmark (the leaderboard)."""
    d = transport.get_json(f"{base()}/leaderboard/{benchmark_id}")
    out = []
    for key in ("reference", "reference_advanced"):
        s = d.get(key) if isinstance(d, dict) else None
        if isinstance(s, dict):
            out.append({**s, "_kind": key})
    for s in _items(d, "solutions", "submissions", "leaderboard"):
        out.append(s)
    return out


def overview() -> Dict:
    return transport.get_json(f"{base()}/overview")
