"""The Machine Agent RSI harness loop — deterministic operation-routing search.

Runs on the owner's HOST: pure Python, no client/sandbox/network. Learns extra
operation-selection keywords from labeled cases, validates on a held-out split,
and RECOMMENDS an owner-gated policy bump. Mutates no default; executes nothing.

SAFETY hard gate: never route a true out-of-scope intent (expected None) to a
real operation. A candidate that does is disqualified. (This is defense in depth
— run_machine also gates every consequential op with approve() downstream of
selection, so no routing policy can cause an unapproved action regardless.)
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ai4science.harness.agents.machine.operations import default_operations
from ai4science.harness.agents.machine.policy import OperationPolicy, incumbent_operation_policy
from ai4science.harness.agents.machine.bench import TRAIN_CASES, VAL_CASES

_STOP = frozenset(
    "the this that for from into onto out about please can will to me my a an of on in "
    "and or with your some any now it is are be do i you".split()
)


def _route(policy: OperationPolicy, intent: str, registry) -> Optional[str]:
    op = policy.select(intent, registry)
    return op.name if op is not None else None


def score_routing(policy: OperationPolicy, cases: List[dict], registry=None) -> dict:
    registry = registry if registry is not None else default_operations()
    correct = gap_violations = 0
    in_scope = in_scope_ok = 0
    for c in cases:
        exp = c["expected"]
        got = _route(policy, c["intent"], registry)
        if got == exp:
            correct += 1
        if exp is None and got is not None:
            gap_violations += 1
        if exp is not None:
            in_scope += 1
            if got == exp:
                in_scope_ok += 1
    n = len(cases) or 1
    return {"accuracy": correct / n,
            "coverage": (in_scope_ok / in_scope) if in_scope else 0.0,
            "safety_ok": gap_violations == 0,
            "gap_violations": gap_violations, "n": len(cases)}


def _salient(intent: str) -> Tuple[str, ...]:
    toks = re.split(r"[^a-z0-9]+", (intent or "").lower())
    return tuple(sorted({t for t in toks if len(t) > 2 and t not in _STOP and not t.isdigit()}))


def propose_candidates(policy: OperationPolicy, train_cases: List[dict], registry=None) -> List[tuple]:
    registry = registry if registry is not None else default_operations()
    cands, seen = [], set()
    for c in train_cases:
        exp = c["expected"]
        if exp is None:
            continue
        if _route(policy, c["intent"], registry) == exp:
            continue
        existing = set(policy.extra.get(exp, ()))
        new_toks = tuple(t for t in _salient(c["intent"]) if t not in existing)
        if not new_toks:
            continue
        # try each token alone AND the full bundle; the scorer keeps only the safe,
        # accuracy-improving ones (so an over-general token like "claude" that would
        # hijack another op's routing is dropped while a specific one survives).
        variants = [(t,) for t in new_toks]
        if len(new_toks) > 1:
            variants.append(new_toks)
        for toks in variants:
            if (exp, toks) in seen:
                continue
            seen.add((exp, toks))
            cands.append((exp, toks, policy.with_added(exp, toks)))
    return cands


def run_machine_rsi_search(*, train_cases: Optional[List[dict]] = None,
                           val_cases: Optional[List[dict]] = None,
                           registry=None, seed_policy: Optional[OperationPolicy] = None,
                           max_rounds: int = 8, patience: int = 2) -> dict:
    train = train_cases if train_cases is not None else TRAIN_CASES
    val = val_cases if val_cases is not None else VAL_CASES
    registry = registry if registry is not None else default_operations()
    incumbent = incumbent_operation_policy()
    best = seed_policy if seed_policy is not None else incumbent
    best_s = score_routing(best, train, registry)

    rounds = no_improve = 0
    converged = False
    while rounds < max_rounds and no_improve < patience:
        cands = propose_candidates(best, train, registry)
        if not cands:
            converged = True
            break
        rounds += 1
        scored = [(score_routing(p, train, registry), p, name, toks) for name, toks, p in cands]
        improved = [x for x in scored if x[0]["safety_ok"] and x[0]["accuracy"] > best_s["accuracy"]]
        if not improved:
            no_improve += 1
            continue
        improved.sort(key=lambda x: (x[0]["accuracy"], x[0]["coverage"], x[2], x[3]))
        best_s, best = improved[-1][0], improved[-1][1]
        no_improve = 0
    if no_improve >= patience:
        converged = True

    inc_val = score_routing(incumbent, val, registry)
    best_val = score_routing(best, val, registry)
    adopt = bool(best_val["safety_ok"]
                 and best_val["accuracy"] >= inc_val["accuracy"]
                 and best_val["coverage"] >= inc_val["coverage"]
                 and (best_val["accuracy"] > inc_val["accuracy"] or best_val["coverage"] > inc_val["coverage"]))
    return {
        "best_policy": best.as_map(),
        "learned": best.added_since(incumbent),
        "train_accuracy": best_s["accuracy"],
        "val_accuracy": best_val["accuracy"],
        "incumbent_val_accuracy": inc_val["accuracy"],
        "val_coverage": best_val["coverage"],
        "incumbent_val_coverage": inc_val["coverage"],
        "safety_ok": bool(best_val["safety_ok"] and inc_val["safety_ok"]),
        "adopt": adopt, "rounds": rounds, "converged": converged,
    }
