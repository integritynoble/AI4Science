"""Registry router + registry-as-standard gate.

Resolve a science problem to its L1->L2->L3 lineage in the PWM registry; if a
solved benchmark answers it, return the answer + a physicsworldmodel.org link;
otherwise signal contribute-to-earn. `standard_check` enforces the registry as
the bar an agent's result must meet-or-beat (reward-gate; below-standard results
are still reported, just not reward-eligible).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ai4science.harness import pwm_data


def _site_base() -> str:
    return os.environ.get("PWM_SITE_BASE",
                          "https://explorer.physicsworldmodel.org").rstrip("/")


_LAYER_SEG = {"L1": "principle", "L2": "spec", "L3": "benchmark", "L4": "solution"}


def _layer_of(artifact_id: str) -> str:
    pre = str(artifact_id).split("-", 1)[0].upper()
    return pre if pre in _LAYER_SEG else ""


def artifact_url(artifact_id: str) -> str:
    seg = _LAYER_SEG.get(_layer_of(artifact_id), "artifact")
    return f"{_site_base()}/{seg}/{artifact_id}"


def _node(layer: str, artifact_id: str, title: str = "") -> Dict[str, str]:
    return {"layer": layer, "artifact_id": artifact_id, "title": title or "",
            "url": artifact_url(artifact_id)}


def _flat(d: Dict[str, Any]) -> Dict[str, Any]:
    """Accept either the flat documented shape or the live shape that nests the
    record under 'genesis'/'principle'/'spec'. Prefer top-level keys."""
    if not isinstance(d, dict):
        return {}
    inner = d.get("genesis") or d.get("principle") or d.get("spec") or {}
    if isinstance(inner, dict):
        merged = dict(inner)
        merged.update({k: v for k, v in d.items() if k not in ("genesis", "principle", "spec")})
        return merged
    return d


def resolve_lineage(artifact_id: str) -> List[Dict[str, str]]:
    """Root-first ancestry [L1, (L2), (L3)] via parent_l1/parent_l2 pointers."""
    layer = _layer_of(artifact_id)
    chain: List[Dict[str, str]] = []
    if layer == "L3":
        b = _flat(pwm_data.benchmark(artifact_id) or {})
        if b.get("parent_l1"):
            chain.append(_node("L1", b["parent_l1"]))
        if b.get("parent_l2"):
            chain.append(_node("L2", b["parent_l2"]))
        chain.append(_node("L3", artifact_id, b.get("title", "")))
    elif layer == "L2":
        s = _flat(pwm_data.spec(artifact_id) or {})
        if s.get("parent_l1"):
            chain.append(_node("L1", s["parent_l1"]))
        chain.append(_node("L2", artifact_id, s.get("title", "")))
    elif layer == "L1":
        chain.append(_node("L1", artifact_id))
    return chain


def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def best_solution(benchmark_id: str, metric_field: str = "psnr_db",
                  higher_is_better: bool = True) -> Optional[Dict[str, Any]]:
    """The leaderboard-best registered solution for a benchmark (or None)."""
    scored = [(s, _num(s.get(metric_field))) for s in pwm_data.solutions(benchmark_id)]
    scored = [(s, v) for s, v in scored if v is not None]
    if not scored:
        return None
    return (max if higher_is_better else min)(scored, key=lambda t: t[1])[0]


def find_problem(query: str) -> Dict[str, Any]:
    """Resolve a problem to a registry node. If a solved benchmark matches,
    return its answer + link; else offer contribute-to-earn."""
    res = pwm_data.search(query) or {}
    benches = res.get("benchmarks") or []
    specs = res.get("specs") or []
    prins = res.get("principles") or []

    if benches:
        bid = benches[0]["artifact_id"]
        ans = best_solution(bid)
        return {"query": query, "matched": True, "match_layer": "L3",
                "artifact_id": bid, "title": benches[0].get("title", ""),
                "lineage": resolve_lineage(bid), "url": artifact_url(bid),
                "exists": ans is not None, "answer": ans,
                "contribute": ans is None,
                "contribute_hint": ("" if ans is not None else
                    "Benchmark exists but has no registered solution — contribute a "
                    "solution that meets-or-beats to earn PWM.")}
    if specs:
        sid = specs[0]["artifact_id"]
        return {"query": query, "matched": True, "match_layer": "L2",
                "artifact_id": sid, "title": specs[0].get("title", ""),
                "lineage": resolve_lineage(sid), "url": artifact_url(sid),
                "exists": False, "answer": None, "contribute": True,
                "contribute_hint": "A digital twin exists but no benchmark/solution — "
                "contribute a benchmark + solution to earn PWM."}
    if prins:
        pid = prins[0]["artifact_id"]
        return {"query": query, "matched": True, "match_layer": "L1",
                "artifact_id": pid, "title": prins[0].get("title", ""),
                "lineage": resolve_lineage(pid), "url": artifact_url(pid),
                "exists": False, "answer": None, "contribute": True,
                "contribute_hint": "A principle exists but no twin/benchmark/solution — "
                "contribute down the chain to earn PWM."}
    return {"query": query, "matched": False, "exists": False, "answer": None,
            "lineage": [], "contribute": True,
            "contribute_hint": "No matching artifact in physicsworldmodel.org. "
            "Contribute a new principle -> digital twin -> benchmark -> solution; "
            "PWM reward scales with the highest new layer you add."}


def standard_check(benchmark_id: str, value: float, metric_field: str = "psnr_db",
                   higher_is_better: bool = True, tol: float = 0.0) -> Dict[str, Any]:
    """Registry-as-standard gate: is `value` at-or-above the leaderboard best?

    Reward-gate semantics: below-standard results are still reported (the caller
    delivers them to the user) but are not reward-eligible.
    """
    best = best_solution(benchmark_id, metric_field, higher_is_better)
    if best is None:
        return {"benchmark_id": benchmark_id, "metric": metric_field, "value": value,
                "leaderboard_best": None, "meets_or_beats": True,
                "reward_eligible": True, "delta": None, "url": artifact_url(benchmark_id),
                "note": "No registered solution yet — any valid result sets the standard."}
    bv = _num(best.get(metric_field))
    meets = (value >= bv - tol) if higher_is_better else (value <= bv + tol)
    delta = value - bv
    note = ("At or above the registry standard." if meets else
            f"BELOW the registry standard: leaderboard best {metric_field}={bv}, "
            f"yours={value} (delta {delta:+.4g}). Result delivered to the user, but "
            "not reward-eligible until it meets-or-beats the best.")
    return {"benchmark_id": benchmark_id, "metric": metric_field, "value": value,
            "leaderboard_best": bv, "best_label": best.get("label", ""),
            "meets_or_beats": meets, "delta": delta, "reward_eligible": meets,
            "url": artifact_url(benchmark_id), "note": note}
