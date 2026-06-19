from __future__ import annotations

import json
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


def _unwrap(d):
    """The detail endpoints wrap stubs as {'detail': …}; unwrap that single key
    but keep rich responses ({principle, specs, registered_benchmarks, …}) whole
    so the caller sees a principle's digital twins (specs) + benchmarks inline."""
    if isinstance(d, dict) and list(d.keys()) == ["detail"]:
        return d["detail"]
    return d


def principle(artifact_id: str) -> Dict:
    # full detail: principle metadata + its specs (digital twins) + benchmarks
    return _unwrap(transport.get_json(f"{base()}/principles/{artifact_id}"))


def benchmarks() -> List[Dict]:
    return _items(transport.get_json(f"{base()}/benchmarks"), "genesis", "benchmarks")


def benchmark(ref: str) -> Dict:
    return _unwrap(transport.get_json(f"{base()}/benchmarks/{ref}"))


def specs() -> List[Dict]:
    """Active digital-twin specs (L2) — the forward-model setups under principles."""
    return _items(transport.get_json(f"{base()}/specs"), "genesis", "specs", "chain")


def spec(artifact_id: str) -> Dict:
    """A digital-twin spec's full detail (six_tuple, protocol_fields, d_spec, …)."""
    d = _unwrap(transport.get_json(f"{base()}/specs/{artifact_id}"))
    return d.get("spec", d) if isinstance(d, dict) and "spec" in d else d


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


def search(query: str, *, limit: int = 20) -> Dict:
    """Keyword-search the registry across principles + benchmarks (client-side —
    the explorer API has no search endpoint). Case-insensitive substring match
    over each item's full content. Use this to GROUND a research question before
    listing the whole registry. Returns {query, principles[], benchmarks[]}."""
    q = (query or "").strip().lower()

    def _match(items: List[Dict]) -> List[Dict]:
        out: List[Dict] = []
        for it in items:
            if not q or q in json.dumps(it, default=str).lower():
                out.append(it)
                if len(out) >= limit:
                    break
        return out

    try:
        prins = _match(principles())
    except Exception:
        prins = []
    try:
        twins = _match(specs())
    except Exception:
        twins = []
    try:
        benches = _match(benchmarks())
    except Exception:
        benches = []
    return {"query": query, "principles": prins, "specs": twins, "benchmarks": benches}
