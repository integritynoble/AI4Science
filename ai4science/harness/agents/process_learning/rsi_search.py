"""The Work-Process Learning RSI harness loop — 1-D grounding-strictness search.

Runs on the owner's HOST: pure Python, no client/sandbox/network. It tunes the
grounding gate's `min_claim_words` (the strictness knob added to research_check)
against a labeled accept/reject benchmark, validates on a held-out split, and
RECOMMENDS an owner-gated config bump. It mutates no default and executes nothing.

The SAFETY hard gate is asymmetric and never tuned: any candidate strictness that
ACCEPTS a fabricated deliverable is disqualified. The loop only picks among
strictness values that reject every fabricated case — so it can reduce false
rejections of valid work (less re-interaction) without ever admitting a
hallucination.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from ai4science.harness.agents.research.research_check import check_research, sha256_file
from ai4science.harness.agents.process_learning.bench import (
    TRAIN_CASES, VAL_CASES, INCUMBENT_MIN_CLAIM, SEARCH_LO, SEARCH_HI,
)


def _gate(case: dict, min_claim: int) -> bool:
    """Materialize the case into a temp workspace and return the REAL gate verdict."""
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        ws = Path(d)
        shas = {}
        for fname, text in case["sources"].items():
            (ws / fname).write_text(text)
            shas[fname] = sha256_file(ws / fname)
        (ws / "report.md").write_text(case["report"])
        config = {"report": "report.md", "sources": shas, "coverage_points": [],
                  "min_claim_words": min_claim}
        return check_research(ws, config)["ok"]


def score_strictness(min_claim: int, cases: List[dict]) -> dict:
    """accuracy = fraction whose verdict matches expected_ok; safety_ok = no
    fabricated case was accepted; autonomy = fraction of VALID cases accepted."""
    correct = accepted_fabricated = 0
    valid = valid_accepted = 0
    for c in cases:
        ok = _gate(c, min_claim)
        if ok == c["expected_ok"]:
            correct += 1
        if (not c["expected_ok"]) and ok:
            accepted_fabricated += 1
        if c["expected_ok"]:
            valid += 1
            if ok:
                valid_accepted += 1
    n = len(cases) or 1
    return {"accuracy": correct / n,
            "autonomy": (valid_accepted / valid) if valid else 0.0,
            "safety_ok": accepted_fabricated == 0,
            "accepted_fabricated": accepted_fabricated,
            "correct": correct, "n": len(cases)}


def _report(inc, best, best_k, adopt) -> str:
    return "\n".join([
        "Process-Learning RSI grounding-strictness search (Host-side, owner-gated):",
        f"  min_claim_words : {INCUMBENT_MIN_CLAIM} (incumbent) -> {best_k} (candidate)",
        f"  val accuracy    : {inc['accuracy']:.3f} -> {best['accuracy']:.3f}",
        f"  val autonomy    : {inc['autonomy']:.3f} -> {best['autonomy']:.3f} "
        f"(valid work accepted)",
        f"  safety_ok       : incumbent={inc['safety_ok']} candidate={best['safety_ok']} "
        f"(no fabricated deliverable ever accepted)",
        f"  RECOMMENDATION  : {'ADOPT' if adopt else 'do not adopt'} "
        f"(owner confirms before adopting the gate config)",
    ])


def run_process_learning_rsi_search(*, train_cases: Optional[List[dict]] = None,
                                    val_cases: Optional[List[dict]] = None,
                                    lo: int = SEARCH_LO, hi: int = SEARCH_HI) -> dict:
    """Exhaustive 1-D search over min_claim_words in [lo, hi]. Keep only SAFE
    strictness values (reject all fabricated on TRAIN), pick the best train
    accuracy (tie-break: smallest / most conservative threshold), then validate
    on the held-out split. Recommends adoption; mutates no default."""
    train = train_cases if train_cases is not None else TRAIN_CASES
    val = val_cases if val_cases is not None else VAL_CASES

    safe = []
    for k in range(lo, hi + 1):
        s = score_strictness(k, train)
        if s["safety_ok"]:
            safe.append((s["accuracy"], -k, k, s))     # -k => tie-break smallest k
    if safe:
        safe.sort()
        best_k = safe[-1][2]
    else:
        best_k = INCUMBENT_MIN_CLAIM                    # fail safe to the shipped value

    inc_val = score_strictness(INCUMBENT_MIN_CLAIM, val)
    best_val = score_strictness(best_k, val)
    adopt = bool(
        best_val["safety_ok"]
        and best_val["accuracy"] >= inc_val["accuracy"]
        and best_val["autonomy"] >= inc_val["autonomy"]
        and (best_val["accuracy"] > inc_val["accuracy"]
             or best_val["autonomy"] > inc_val["autonomy"])
    )
    return {
        "best_min_claim_words": best_k,
        "incumbent_min_claim_words": INCUMBENT_MIN_CLAIM,
        "train_accuracy": score_strictness(best_k, train)["accuracy"],
        "val_accuracy": best_val["accuracy"],
        "incumbent_val_accuracy": inc_val["accuracy"],
        "val_autonomy": best_val["autonomy"],
        "incumbent_val_autonomy": inc_val["autonomy"],
        "safety_ok": bool(best_val["safety_ok"] and inc_val["safety_ok"]),
        "adopt": adopt,
        "report": _report(inc_val, best_val, best_k, adopt),
    }
