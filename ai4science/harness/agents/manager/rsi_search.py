"""The Manager's RSI harness-engineering loop — pure, deterministic, LLM-free.

Runs on the owner's HOST: no client, no sandbox, no network. It learns extra
scope-router keywords from labeled routing cases, validates on a held-out split,
and RECOMMENDS adoption (an owner-gated policy version bump). It mutates no
default and executes nothing — routing a demand is still only a proposal.

Mirrors pocket/rsi_search.py: coordinate-descent over a keyword policy with a
SAFETY hard gate. Here the invariant is "never fabricate a recommendation for a
true out-of-domain gap": any candidate that routes an expected-gap case to an
agent is disqualified, regardless of accuracy.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ai4science.harness.agents.manager.routing_policy import RoutePolicy, incumbent_route_policy
from ai4science.harness.agents.manager.bench import SPECS, TRAIN_CASES, VAL_CASES

_STOP = frozenset(
    "the this that some any and or with for from into onto out about these those "
    "help you your our them please can will would should our their its".split()
)


def _primary(policy: RoutePolicy, intent: str, specs) -> Optional[str]:
    return policy.route(intent, specs)["primary"]


def score_routing(policy: RoutePolicy, cases: List[dict], specs=SPECS) -> dict:
    """accuracy = fraction routed to the expected agent (None == gap); coverage =
    fraction of in-domain cases correctly routed; safety_ok = no expected-gap case
    routed to an agent (no fabricated recommendation)."""
    correct = gap_violations = 0
    in_domain = in_domain_ok = 0
    for c in cases:
        exp = c["expected"]
        got = _primary(policy, c["intent"], specs)
        if got == exp:
            correct += 1
        if exp is None and got is not None:
            gap_violations += 1
        if exp is not None:
            in_domain += 1
            if got == exp:
                in_domain_ok += 1
    n = len(cases) or 1
    return {"accuracy": correct / n,
            "coverage": (in_domain_ok / in_domain) if in_domain else 0.0,
            "safety_ok": gap_violations == 0,
            "gap_violations": gap_violations,
            "correct": correct, "n": len(cases)}


def _salient_tokens(intent: str) -> Tuple[str, ...]:
    toks = re.split(r"[^a-z0-9]+", (intent or "").lower())
    return tuple(sorted({t for t in toks if len(t) > 2 and t not in _STOP and not t.isdigit()}))


def propose_candidates(policy: RoutePolicy, train_cases: List[dict], specs=SPECS) -> List[tuple]:
    """For each in-domain train case the current policy misroutes, propose adding
    its salient tokens to the EXPECTED agent's keyword set. Gap cases are never
    mined (gaps must stay gaps). Deterministic; deduped."""
    cands: List[tuple] = []
    seen = set()
    for c in train_cases:
        exp = c["expected"]
        if exp is None:
            continue
        if _primary(policy, c["intent"], specs) == exp:
            continue  # already correct
        existing = set(policy.extra.get(exp, ()))
        new_toks = tuple(t for t in _salient_tokens(c["intent"]) if t not in existing)
        if not new_toks:
            continue
        key = (exp, new_toks)
        if key in seen:
            continue
        seen.add(key)
        cands.append((exp, new_toks, policy.with_added(exp, new_toks)))
    return cands


def _report(inc_val: dict, best_val: dict, learned, adopt, rounds, converged) -> str:
    lines = [
        "Manager RSI scope-router search (Host-side, owner-gated):",
        f"  rounds={rounds} converged={converged}",
        f"  val accuracy : {inc_val['accuracy']:.3f} (incumbent) -> {best_val['accuracy']:.3f} (candidate)",
        f"  val coverage : {inc_val['coverage']:.3f} (incumbent) -> {best_val['coverage']:.3f} (candidate)",
        f"  safety_ok    : incumbent={inc_val['safety_ok']} candidate={best_val['safety_ok']} "
        f"(no fabricated recommendation for a gap)",
        "  learned keywords:",
    ]
    if learned:
        for name in sorted(learned):
            lines.append(f"    {name}: {', '.join(learned[name])}")
    else:
        lines.append("    (none)")
    lines.append(f"  RECOMMENDATION: {'ADOPT' if adopt else 'do not adopt'} "
                 f"(owner confirms before adopting the router policy)")
    return "\n".join(lines)


def run_manager_rsi_search(*, train_cases: Optional[List[dict]] = None,
                           val_cases: Optional[List[dict]] = None,
                           specs=None, seed_policy: Optional[RoutePolicy] = None,
                           max_rounds: int = 8, patience: int = 2) -> dict:
    """Coordinate-descent over router keyword policies: propose from the current
    best's misroutes, score on TRAIN, keep only safe + strictly-accuracy-improving
    candidates, adopt the best. Then a validation round on the untouched VAL split
    decides the `adopt` recommendation. Mutates no default; executes nothing."""
    train = train_cases if train_cases is not None else TRAIN_CASES
    val = val_cases if val_cases is not None else VAL_CASES
    specs = specs if specs is not None else SPECS
    incumbent = incumbent_route_policy()
    best = seed_policy if seed_policy is not None else incumbent
    best_s = score_routing(best, train, specs)

    rounds = no_improve = 0
    converged = False
    while rounds < max_rounds and no_improve < patience:
        cands = propose_candidates(best, train, specs)
        if not cands:
            converged = True
            break
        rounds += 1
        scored = []
        for name, toks, pol in cands:
            s = score_routing(pol, train, specs)
            if s["safety_ok"] and s["accuracy"] > best_s["accuracy"]:
                scored.append((s, pol, name, toks))
        if not scored:
            no_improve += 1
            continue
        scored.sort(key=lambda x: (x[0]["accuracy"], x[0]["coverage"], x[2], x[3]))
        best_s, best = scored[-1][0], scored[-1][1]
        no_improve = 0
    if no_improve >= patience:
        converged = True

    inc_val = score_routing(incumbent, val, specs)
    best_val = score_routing(best, val, specs)
    adopt = bool(
        best_val["safety_ok"]
        and best_val["accuracy"] >= inc_val["accuracy"]
        and best_val["coverage"] >= inc_val["coverage"]
        and (best_val["accuracy"] > inc_val["accuracy"]
             or best_val["coverage"] > inc_val["coverage"])
    )
    learned = best.added_since(incumbent)
    return {
        "best_policy": best.as_map(),
        "learned": learned,
        "train_accuracy": best_s["accuracy"],
        "val_accuracy": best_val["accuracy"],
        "incumbent_val_accuracy": inc_val["accuracy"],
        "val_coverage": best_val["coverage"],
        "incumbent_val_coverage": inc_val["coverage"],
        "safety_ok": bool(best_val["safety_ok"] and inc_val["safety_ok"]),
        "adopt": adopt,
        "rounds": rounds,
        "converged": converged,
        "report": _report(inc_val, best_val, learned, adopt, rounds, converged),
    }
