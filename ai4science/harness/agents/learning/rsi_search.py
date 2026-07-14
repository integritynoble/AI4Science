"""The Personal Learning RSI harness loop — 1-D quiz-quality-floor search.

Runs on the owner's HOST: pure Python, no client/sandbox/network. It tunes the
quiz gate's `min_questions` (a quality floor) against a labeled accept/reject
benchmark, validates on a held-out split, and RECOMMENDS an owner-gated config
bump. Mutates no default; executes nothing.

The grounding guarantee (every answer verbatim-supported by a source) is the
SAFETY floor and is INDEPENDENT of this knob: an ungrounded quiz is rejected at
every min_questions. The loop verifies that (safety_ok holds at all values) and
picks the floor that best separates adequate from inadequate quizzes.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

from ai4science.harness.agents.learning.quiz_check import check_quiz, sha256_file
from ai4science.harness.agents.learning.bench import (
    TRAIN_CASES, VAL_CASES, INCUMBENT_MIN_QUESTIONS, SEARCH_LO, SEARCH_HI,
)


def _gate(case: dict, min_questions: int) -> bool:
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        ws = Path(d)
        shas = {}
        for fname, text in case["sources"].items():
            (ws / fname).write_text(text)
            shas[fname] = sha256_file(ws / fname)
        (ws / "study_guide.md").write_text(case["guide"])
        (ws / "quiz.json").write_text(case["quiz"])
        config = {"sources": shas, "min_questions": min_questions,
                  "study_guide": "study_guide.md", "quiz": "quiz.json", "coverage_points": []}
        return check_quiz(ws, config)["ok"]


def score_floor(min_questions: int, cases: List[dict]) -> dict:
    """accuracy = fraction whose verdict matches expected_ok; safety_ok = no
    fabricated (ungrounded) quiz accepted; autonomy = fraction of VALID quizzes
    accepted."""
    correct = accepted_fabricated = 0
    valid = valid_accepted = 0
    for c in cases:
        ok = _gate(c, min_questions)
        if ok == c["expected_ok"]:
            correct += 1
        if c["kind"] == "fabricated" and ok:
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
        "Personal-Learning RSI quiz-quality-floor search (Host-side, owner-gated):",
        f"  min_questions : {INCUMBENT_MIN_QUESTIONS} (incumbent) -> {best_k} (candidate)",
        f"  val accuracy  : {inc['accuracy']:.3f} -> {best['accuracy']:.3f}",
        f"  val autonomy  : {inc['autonomy']:.3f} -> {best['autonomy']:.3f} (valid quizzes accepted)",
        f"  safety_ok     : incumbent={inc['safety_ok']} candidate={best['safety_ok']} "
        f"(ungrounded quiz never accepted, at any floor)",
        f"  RECOMMENDATION: {'ADOPT' if adopt else 'do not adopt'} "
        f"(owner confirms before adopting the gate config)",
    ])


def run_learning_rsi_search(*, train_cases: Optional[List[dict]] = None,
                            val_cases: Optional[List[dict]] = None,
                            lo: int = SEARCH_LO, hi: int = SEARCH_HI) -> dict:
    """Exhaustive 1-D search over min_questions in [lo, hi]: keep SAFE floors
    (reject all fabricated on TRAIN), pick best train accuracy (tie-break: smallest
    floor), then validate on the held-out split. Recommends adoption; mutates no
    default."""
    train = train_cases if train_cases is not None else TRAIN_CASES
    val = val_cases if val_cases is not None else VAL_CASES

    safe = []
    for k in range(lo, hi + 1):
        s = score_floor(k, train)
        if s["safety_ok"]:
            safe.append((s["accuracy"], -k, k))        # -k => tie-break smallest floor
    best_k = safe[-1][2] if (safe := sorted(safe)) else INCUMBENT_MIN_QUESTIONS

    inc_val = score_floor(INCUMBENT_MIN_QUESTIONS, val)
    best_val = score_floor(best_k, val)
    adopt = bool(
        best_val["safety_ok"]
        and best_val["accuracy"] >= inc_val["accuracy"]
        and best_val["autonomy"] >= inc_val["autonomy"]
        and best_val["accuracy"] > inc_val["accuracy"]
    )
    return {
        "best_min_questions": best_k,
        "incumbent_min_questions": INCUMBENT_MIN_QUESTIONS,
        "train_accuracy": score_floor(best_k, train)["accuracy"],
        "val_accuracy": best_val["accuracy"],
        "incumbent_val_accuracy": inc_val["accuracy"],
        "val_autonomy": best_val["autonomy"],
        "incumbent_val_autonomy": inc_val["autonomy"],
        "safety_ok": bool(best_val["safety_ok"] and inc_val["safety_ok"]),
        "adopt": adopt,
        "report": _report(inc_val, best_val, best_k, adopt),
    }
