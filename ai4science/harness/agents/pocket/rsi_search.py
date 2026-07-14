"""The Pocket agent's RSI harness-engineering loop — pure, deterministic, LLM-free.

Runs on the owner's HOST (Tier H): no client, no sandbox, no network. It learns a
better keyword->tool policy from labeled examples, validates it on a held-out
split, and RECOMMENDS adoption. It mutates no default and performs no action —
the owner reviews the report and ships the adopted policy to the phone (a policy
version bump). Adoption is the owner's gate; the loop only proposes.

Shape mirrors imaging/rsi_search.py::run_rsi_search (search rounds -> validation
round -> owner-gated adopt), with two Tier-D differences: the knob is a
KeywordPolicy (not a numeric config), and the scorer enforces an asymmetric
SAFETY hard gate — any candidate that under-refuses a consequential intent is
disqualified regardless of accuracy.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ai4science.harness.agents.pocket.agent import run_pocket
from ai4science.harness.agents.pocket.policy import KeywordPolicy, incumbent_policy
from ai4science.harness.agents.pocket.bench import TRAIN_CASES, VAL_CASES

_STOP = frozenset(
    "a an the to of my me i is this that for on in it please can you do what "
    "whats and or with about your some any".split()
)


def _outcome(out: dict) -> tuple:
    st = out["status"]
    if st == "done":
        return ("done", out["tool"])
    if st == "handoff":
        return ("handoff", out["kind"])
    if st == "refused":
        return ("refused", out["tool"])
    return ("advised",)


def _run(policy: KeywordPolicy, case: dict) -> dict:
    # fresh ctx per case so note/reminder stores never bleed across the benchmark.
    return run_pocket(intent=case["intent"], granted=case.get("granted", ()),
                      select=policy.select, ctx={})


def score_policy(policy: KeywordPolicy, cases: List[dict]) -> dict:
    """accuracy = fraction matching `expected`; autonomy = fraction resolved to a
    direct `done`; safety_ok = no consequential case failed to hand off."""
    correct = direct = safety_violations = 0
    for c in cases:
        out = _run(policy, c)
        exp = tuple(c["expected"])
        if _outcome(out) == exp:
            correct += 1
        if out["status"] == "done":
            direct += 1
        if exp[0] == "handoff" and out["status"] != "handoff":
            safety_violations += 1
    n = len(cases) or 1
    return {"accuracy": correct / n, "autonomy": direct / n,
            "safety_ok": safety_violations == 0,
            "safety_violations": safety_violations,
            "correct": correct, "n": len(cases)}


def _salient_tokens(intent: str) -> Tuple[str, ...]:
    toks = re.split(r"[^a-z0-9]+", (intent or "").lower())
    return tuple(sorted({t for t in toks if len(t) >= 3 and t not in _STOP and not t.isdigit()}))


def propose_candidates(policy: KeywordPolicy, train_cases: List[dict]) -> List[tuple]:
    """For each train case that SHOULD be `done` but the current policy misses,
    propose adding its salient tokens to the target tool. Deterministic; deduped."""
    cands: List[tuple] = []
    seen = set()
    for c in train_cases:
        exp = tuple(c["expected"])
        if exp[0] != "done":
            continue
        if _outcome(_run(policy, c)) == exp:
            continue  # already correct
        tool = exp[1]
        existing = set(policy.keyword_map.get(tool, ()))
        new_toks = tuple(t for t in _salient_tokens(c["intent"]) if t not in existing)
        if not new_toks:
            continue
        key = (tool, new_toks)
        if key in seen:
            continue
        seen.add(key)
        cands.append((tool, new_toks, policy.with_added(tool, new_toks)))
    return cands


def _report(inc_val: dict, best_val: dict, learned: Dict[str, Tuple[str, ...]],
            adopt: bool, rounds: int, converged: bool) -> str:
    lines = [
        "Pocket RSI harness search (Host-side, owner-gated):",
        f"  rounds={rounds} converged={converged}",
        f"  val accuracy : {inc_val['accuracy']:.3f} (incumbent) -> {best_val['accuracy']:.3f} (candidate)",
        f"  val autonomy : {inc_val['autonomy']:.3f} (incumbent) -> {best_val['autonomy']:.3f} (candidate)",
        f"  safety_ok    : incumbent={inc_val['safety_ok']} candidate={best_val['safety_ok']}",
        "  learned phrases:",
    ]
    if learned:
        for tool in sorted(learned):
            lines.append(f"    {tool}: {', '.join(learned[tool])}")
    else:
        lines.append("    (none)")
    lines.append(f"  RECOMMENDATION: {'ADOPT' if adopt else 'do not adopt'} "
                 f"(owner confirms before shipping to the phone)")
    return "\n".join(lines)


def run_pocket_rsi_search(*, train_cases: Optional[List[dict]] = None,
                          val_cases: Optional[List[dict]] = None,
                          seed_policy: Optional[KeywordPolicy] = None,
                          max_rounds: int = 8, patience: int = 2) -> dict:
    """Coordinate-descent over keyword policies. Each round: propose candidates
    from the current best's remaining misses, score on TRAIN, keep only safe and
    strictly-accuracy-improving candidates, adopt the best. Stop on convergence
    (no candidates / patience) or budget. Then a validation round on the untouched
    VAL split decides the `adopt` recommendation. Returns the winning policy map,
    the learned diff, both splits' scores, and a human-readable report. Executes
    nothing and mutates no default."""
    train = train_cases if train_cases is not None else TRAIN_CASES
    val = val_cases if val_cases is not None else VAL_CASES
    incumbent = incumbent_policy()
    best = seed_policy if seed_policy is not None else incumbent
    best_s = score_policy(best, train)

    rounds = no_improve = 0
    converged = False
    while rounds < max_rounds and no_improve < patience:
        cands = propose_candidates(best, train)
        if not cands:
            converged = True
            break
        rounds += 1
        scored = []
        for tool, toks, pol in cands:
            s = score_policy(pol, train)
            # asymmetric SAFETY hard gate + strict accuracy improvement
            if s["safety_ok"] and s["accuracy"] > best_s["accuracy"]:
                scored.append((s, pol, tool, toks))
        if not scored:
            no_improve += 1
            continue
        # deterministic pick: highest accuracy, then autonomy, then tool, then toks
        scored.sort(key=lambda x: (x[0]["accuracy"], x[0]["autonomy"], x[2], x[3]))
        best_s, best = scored[-1][0], scored[-1][1]
        no_improve = 0
    if no_improve >= patience:
        converged = True

    inc_val = score_policy(incumbent, val)
    best_val = score_policy(best, val)
    adopt = bool(
        best_val["safety_ok"]
        and best_val["accuracy"] >= inc_val["accuracy"]
        and best_val["autonomy"] >= inc_val["autonomy"]
        and (best_val["accuracy"] > inc_val["accuracy"]
             or best_val["autonomy"] > inc_val["autonomy"])
    )
    learned = best.added_since(incumbent)
    return {
        "best_policy": best.as_map(),
        "learned": learned,
        "train_accuracy": best_s["accuracy"],
        "val_accuracy": best_val["accuracy"],
        "incumbent_val_accuracy": inc_val["accuracy"],
        "val_autonomy": best_val["autonomy"],
        "incumbent_val_autonomy": inc_val["autonomy"],
        "safety_ok": bool(best_val["safety_ok"] and inc_val["safety_ok"]),
        "adopt": adopt,
        "rounds": rounds,
        "converged": converged,
        "report": _report(inc_val, best_val, learned, adopt, rounds, converged),
    }
