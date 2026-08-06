"""Proposing candidates, and deciding whether one is actually better.

The first autonomous night ran correctly and found nothing, because nothing
proposed a variant: every round scored the incumbent against itself and reported
a delta of zero. This is the missing half.

Three things make the difference between a search and a way of manufacturing
results:

**Paired comparison.** Candidate and incumbent run on the *same* seeds, and the
delta is taken per seed. Comparing two means over different seeds measures the
seeds as much as the method — and in these fields the seed spread is often
larger than the effect, which is the whole reason `Improvement` exists.

**Selection and validation are different seeds.** The winner of a search is the
maximum of a noisy sample, so its search score is biased upward by the act of
choosing it. It is re-run on seeds never used for selection, and *that* number
is the claim. The imaging agent had this right first (`rsi_search`'s separate
search and validation domains).

**Guardrails are checked, not hoped for.** A field's characteristic bad trade —
fidelity bought with detectability, enrichment bought from a property bias — is
exactly what an optimiser finds first. A candidate that improves the objective
while a guardrail metric degrades is rejected, and the rejection says which one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .runners.common import DomainBenchmark, Parameter

#: Below this, a validation set cannot support a claim. Two seeds gave a spread
#: of 1.54 on an effect of 1.31 in the first searching night — an interval that
#: wide is not evidence, it is a shrug with a number attached.
MIN_VALIDATION_SEEDS = 4


def paired_p(deltas: Sequence[float]) -> Optional[float]:
    """Two-sided paired t-test on the per-seed deltas.

    Paired because candidate and incumbent ran on the same seeds: the pairing is
    what removes the seed-to-seed variation that would otherwise swamp the
    effect. An unpaired test here would be answering a different question."""
    n = len(deltas)
    if n < 2:
        return None
    m = sum(deltas) / n
    sd = math.sqrt(sum((d - m) ** 2 for d in deltas) / (n - 1))
    if sd == 0.0:
        return 0.0 if m != 0.0 else 1.0
    t = m / (sd / math.sqrt(n))
    try:
        from scipy import stats
        return float(2.0 * stats.t.sf(abs(t), n - 1))
    except Exception:
        # Normal approximation rather than no answer; flagged by the caller.
        return float(2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2)))))


@dataclass
class Candidate:
    """One proposed setting of the method's knobs."""
    params: Dict[str, float]
    origin: str = ""                      # how it was proposed, for the log

    def key(self) -> str:
        return " ".join("%s=%g" % (k, self.params[k]) for k in sorted(self.params))


class CoordinateSearch:
    """Move one knob at a time, shrinking the step when a round finds nothing.

    Deliberately simple and deliberately *not* adaptive on the validation set:
    an optimiser that could see the held-out scores would be selecting on them,
    which is the thing holding them out was for."""

    def __init__(self, bench: DomainBenchmark, *, step: float = 0.5):
        self.bench = bench
        self.step = step

    def propose(self, incumbent: Dict[str, float], *, tried: set,
                round_no: int) -> List[Candidate]:
        out: List[Candidate] = []
        for p in self.bench.parameters:
            # A knob declared over orders of magnitude is walked multiplicatively.
            # Linear steps across [0.0001, 5000] are ~2500 wide, so every value
            # below 1 is reachable only by clamping to the floor: the search
            # reports that it explored the range while never visiting the part
            # of it where the parameter does anything. Measured on reverse-aging,
            # where widening the floor bought exactly one reachable candidate.
            log = getattr(p, "log", False) and incumbent[p.name] > 0
            if log:
                span = (math.log(p.high) - math.log(p.low)) * self.step / (round_no + 1)
            else:
                span = (p.high - p.low) * self.step / (round_no + 1)
            for direction in (+1, -1):
                if log:
                    v = p.clamp(math.exp(math.log(incumbent[p.name])
                                         + direction * span))
                else:
                    v = p.clamp(incumbent[p.name] + direction * span)
                if v == incumbent[p.name]:
                    continue
                params = dict(incumbent)
                params[p.name] = v
                origin = ("%s %s%.3g" % (p.name, "x" if direction > 0 else "/",
                                         math.exp(span))
                          if log else
                          "%s %s%.3g" % (p.name, "+" if direction > 0 else "-", span))
                c = Candidate(params, origin=origin)
                if c.key() not in tried:
                    out.append(c)
        return out


@dataclass
class Trial:
    """One candidate, scored against the incumbent on the same seeds."""
    candidate: Candidate
    seeds: Tuple[int, ...]
    incumbent_scores: Tuple[float, ...]
    candidate_scores: Tuple[float, ...]
    guardrails: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    @property
    def deltas(self) -> Tuple[float, ...]:
        return tuple(c - i for c, i in zip(self.candidate_scores,
                                           self.incumbent_scores))

    @property
    def mean_delta(self) -> float:
        d = self.deltas
        return sum(d) / len(d) if d else 0.0

    @property
    def spread(self) -> Optional[float]:
        d = self.deltas
        if len(d) < 2:
            return None
        m = self.mean_delta
        return math.sqrt(sum((x - m) ** 2 for x in d) / (len(d) - 1))

    def better(self, higher_is_better: bool) -> bool:
        return (self.mean_delta > 0) if higher_is_better else (self.mean_delta < 0)

    def guardrail_breaches(self, higher_is_better: Dict[str, bool]) -> List[str]:
        out = []
        for name, (inc, cand) in self.guardrails.items():
            up = higher_is_better.get(name, True)
            worse = (cand < inc) if up else (cand > inc)
            if worse:
                out.append("%s went from %.4g to %.4g" % (name, inc, cand))
        return out


def run_search(bench: DomainBenchmark, *, score, incumbent: Dict[str, float],
               search_seeds: Sequence[int], validation_seeds: Sequence[int],
               rounds: int = 2, spend=None,
               guardrail_direction: Optional[Dict[str, bool]] = None,
               prior_validations: int = 0) -> Dict[str, Any]:
    """Search on one seed set, validate the winner on another.

    `score(params, seed) -> dict of metrics` is supplied by the caller so this
    module never touches a sandbox or a corpus. `spend(n_runs)` is called before
    each batch and may raise to stop the search — that is how the budget ends a
    night without this code knowing what a budget is.
    """
    if not bench.parameters:
        return {"searched": False,
                "why": "%s declares no parameters — its method is fixed and "
                       "there is nothing here to search" % bench.agent}
    if not bench.objective:
        return {"searched": False,
                "why": "%s declares no objective; a search with no stated "
                       "target optimises whatever sorts first" % bench.agent}

    if len(validation_seeds) < MIN_VALIDATION_SEEDS:
        return {"searched": False,
                "why": "%d validation seeds is too few to support a claim (need "
                       "%d): a winner selected on one sample and checked against "
                       "a handful of others is still mostly the sample"
                       % (len(validation_seeds), MIN_VALIDATION_SEEDS)}

    obj, up = bench.objective, bench.objective_higher_is_better
    gdir = dict(guardrail_direction or {})
    strategy = CoordinateSearch(bench)
    tried, history = {Candidate(incumbent).key()}, []

    def scores_for(params, seeds):
        rows = [score(params, s) for s in seeds]
        return ([r.get(obj) for r in rows],
                {g: sum(r.get(g, float("nan")) for r in rows) / len(rows)
                 for g in bench.guardrails})

    base_search, base_guards = scores_for(incumbent, search_seeds)
    best = {"params": dict(incumbent), "mean_delta": 0.0, "origin": "incumbent"}

    for rnd in range(rounds):
        cands = strategy.propose(best["params"], tried=tried, round_no=rnd)
        if not cands:
            break
        if spend is not None:
            spend(len(cands) * len(search_seeds))     # may raise: budget ends it
        for c in cands:
            tried.add(c.key())
            cs, cg = scores_for(c.params, search_seeds)
            t = Trial(c, tuple(search_seeds), tuple(base_search), tuple(cs),
                      {g: (base_guards[g], cg[g]) for g in bench.guardrails})
            history.append({"candidate": c.key(), "origin": c.origin,
                            "mean_delta": t.mean_delta,
                            "breaches": t.guardrail_breaches(gdir)})
            if t.better(up) and not t.guardrail_breaches(gdir) \
                    and abs(t.mean_delta) > abs(best["mean_delta"]):
                best = {"params": dict(c.params), "mean_delta": t.mean_delta,
                        "origin": c.origin}

    if best["origin"] == "incumbent":
        return {"searched": True, "improved": False, "history": history,
                "why": "no candidate beat the incumbent on the search seeds"}

    # The winner is the maximum of a noisy sample. Its search score is biased by
    # having been chosen; the honest number comes from seeds it was not chosen on.
    if spend is not None:
        spend(2 * len(validation_seeds))
    inc_val, inc_g = scores_for(incumbent, validation_seeds)
    win_val, win_g = scores_for(best["params"], validation_seeds)
    val = Trial(Candidate(best["params"], best["origin"]), tuple(validation_seeds),
                tuple(inc_val), tuple(win_val),
                {g: (inc_g[g], win_g[g]) for g in bench.guardrails})
    # Multiplicity: the 15 candidates were compared on the SEARCH seeds, and a
    # held-out test after selection is a single unbiased test — correcting it
    # for the search size would double-count. What does need correcting is how
    # many times the night reaches for the validation set: one test per round,
    # each a fresh chance to get lucky. Holm on that count, not on the search.
    raw_p = paired_p(val.deltas)
    tests = prior_validations + 1
    corrected = None if raw_p is None else min(1.0, raw_p * tests)
    return {"searched": True,
            "improved": val.better(up) and (corrected is None or corrected <= 0.05),
            "params": best["params"], "origin": best["origin"],
            "objective": obj, "history": history,
            "search_mean_delta": best["mean_delta"],
            "validation": {"seeds": list(validation_seeds),
                           "incumbent": list(inc_val), "candidate": list(win_val),
                           "mean_delta": val.mean_delta, "spread": val.spread,
                           "p_value": raw_p, "corrected_p": corrected,
                           "validation_tests_this_night": tests,
                           "breaches": val.guardrail_breaches(gdir)},
            "trial": val}
