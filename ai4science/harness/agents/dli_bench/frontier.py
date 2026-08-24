"""The delegation frontier, computed from episodes.

The frontier is the primary result. ``DLn`` is a summary label for it and is
never reported alone, because a label hides the three things a reader needs:
which class, at what reliability, and with how much human time.

Two departures from the usual definition, both deliberate.

**The frontier is a set, not a maximum.** ``max{T : S(T,h) >= p}`` presumes the
set is downward closed -- that a system clearing the bar at T3 clears it at T1.
It is not, because a T band aggregates coordinates that push success in
opposite directions: a short familiar task with no way to check the result is
low-T and undelegable. So :func:`frontier` returns the bands that hold *and*
the lower bands that do not, and :func:`frontier_band` refuses to collapse to a
maximum when there is a gap beneath it.

**Reliability is compared against what the class requires**, not against a
threshold the evaluator picked. ``p_star = rho/(1+rho)`` comes from the task's
loss terms. A benchmark quoting everything at p=0.90 is simultaneously too
strict for cheap-to-undo work and too lenient for the expensive kind.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .spec import BUDGETS, Episode, TaskSpec, budget_index

BANDS: Tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "TOmega")

#: What each level requires: a band, and a budget no looser than this one.
#:
#: "No looser" matters. Holding T2 at H1 is stronger evidence for DL2 than
#: holding it at H2, so it must count -- an earlier version keyed on the exact
#: budget and reported a system that had passed everything at H1 as having
#: established nothing, which is the sort of error a demo catches and a
#: specification does not.
LEVEL_REQ: Dict[str, Tuple[str, str]] = {
    "DL0": ("T0", "H4"),
    "DL1": ("T1", "H3"),
    "DL2": ("T2", "H2"),
    "DL3": ("T3", "H2"),
    "DL4": ("T4", "H1"),
    "DL5": ("T5", "H1"),
    "DL6": ("T6", "H1"),
    "DLOmega": ("TOmega", "H1"),
}

LEVEL_ORDER: Tuple[str, ...] = ("DL0", "DL1", "DL2", "DL3", "DL4",
                                "DL5", "DL6", "DLOmega")

NOT_ESTABLISHED = "none established"

#: Attempts a cell needs before it may establish anything.
#:
#: The anti-inflation rule about heroic runs, enforced rather than stated: a
#: level is a claim about a task family, and one success is a demonstration.
MIN_ATTEMPTS = 5

@dataclass(frozen=True)
class Cell:
    """What happened on one (band, budget) pair."""

    band: str
    budget: str
    attempts: int
    successes: int
    escalations: int
    #: Attempts that were thrown out, with the reason counts.
    inadmissible: int
    p_star: float                   # what the class requires, mean over its tasks
    load_seconds: float             # mean human load per attempt
    max_cid: int
    sigma: float
    verifier_unknown: int           # attempts whose verifier had no false-pass estimate

    @property
    def rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    def wilson(self, z: float = 1.96) -> Tuple[float, float]:
        """Wilson score interval. Reported because a rate from twelve attempts
        and a rate from twelve hundred are not the same claim."""
        n = self.attempts
        if n == 0:
            return (0.0, 0.0)
        p = self.rate
        d = 1 + z * z / n
        c = p + z * z / (2 * n)
        s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        return (max(0.0, (c - s) / d), min(1.0, (c + s) / d))

    def holds(self, p: Optional[float] = None, conservative: bool = True,
              min_attempts: int = MIN_ATTEMPTS) -> bool:
        """Does the system hold this cell?

        ``p`` defaults to the class's own ``p_star``. Three conditions, and all
        three exist because a version without them said yes to something it
        should not have:

        * at least ``min_attempts`` attempts, so a demonstration is not a level;
        * at least one success, because a class whose ``p_star`` is 0 would
          otherwise be held by a system that failed every attempt;
        * the LOWER end of the confidence interval clears the threshold, so a
          lucky short run does not certify.
        """
        need = self.p_star if p is None else p
        if self.attempts < max(1, min_attempts) or self.successes == 0:
            return False
        got = self.wilson()[0] if conservative else self.rate
        return got >= need


def cells(episodes: Sequence[Episode], tasks: Dict[str, TaskSpec]) -> Dict[Tuple[str, str], Cell]:
    """Aggregate episodes into (band, budget) cells.

    Episodes are relabelled to the budget their help actually corresponds to,
    not the one they were launched under: a run intended as H1 that took a
    subproblem strategy is an H3 datum. Relabelling rather than discarding
    keeps the information and refuses the inflation.
    """
    from .policy import demoted_budget

    buckets: Dict[Tuple[str, str], List[Episode]] = defaultdict(list)
    bad: Dict[Tuple[str, str], int] = defaultdict(int)

    for e in episodes:
        ok, _why = e.admissible()
        key0 = (e.band, e.budget)
        if not ok:
            bad[key0] += 1
            continue
        effective = demoted_budget(e.max_cid)
        if budget_index(effective) > budget_index(e.budget):
            key = (e.band, effective)
        else:
            key = (e.band, e.budget)
        buckets[key].append(e)

    out: Dict[Tuple[str, str], Cell] = {}
    for (band, budget), eps in buckets.items():
        ps = [tasks[e.task_id].loss.p_star for e in eps if e.task_id in tasks]
        out[(band, budget)] = Cell(
            band=band,
            budget=budget,
            attempts=len(eps),
            successes=sum(1 for e in eps if e.succeeded),
            escalations=sum(1 for e in eps if e.outcome == "escalated"),
            inadmissible=bad.get((band, budget), 0),
            p_star=(sum(ps) / len(ps)) if ps else 0.5,
            load_seconds=sum(e.load() for e in eps) / len(eps),
            max_cid=max((e.max_cid for e in eps), default=0),
            sigma=sum(e.sigma for e in eps) / len(eps),
            verifier_unknown=sum(1 for e in eps if e.verifier_false_pass_rate is None),
        )
    for key, n in bad.items():
        if key not in out:
            out[key] = Cell(key[0], key[1], 0, 0, 0, n, 0.5, 0.0, 0, 0.0, 0)
    return out


@dataclass(frozen=True)
class Frontier:
    """The bands a system holds at one budget, and the ones beneath it that it does not."""

    budget: str
    p: Optional[float]
    held: Tuple[str, ...]
    failed_below_top: Tuple[str, ...]
    untested: Tuple[str, ...]

    @property
    def contiguous(self) -> bool:
        """True when the held set is downward closed, so a maximum summarises it."""
        return not self.failed_below_top

    def label(self) -> str:
        """The frontier as a string. Refuses to be a single band when it is not one."""
        if not self.held:
            return "none"
        top = max(self.held, key=lambda b: BANDS.index(b))
        if self.contiguous:
            return top
        return "%s with gaps at %s" % (top, ",".join(self.failed_below_top))


def frontier(cs: Dict[Tuple[str, str], Cell], budget: str,
             p: Optional[float] = None) -> Frontier:
    held, failed, untested = [], [], []
    for b in BANDS:
        c = cs.get((b, budget))
        if c is None or c.attempts == 0:
            untested.append(b)
        elif c.holds(p):
            held.append(b)
        else:
            failed.append(b)
    if held:
        top = max(BANDS.index(b) for b in held)
        below = tuple(b for b in failed if BANDS.index(b) < top)
    else:
        below = ()
    return Frontier(budget=budget, p=p, held=tuple(held),
                    failed_below_top=below, untested=tuple(untested))


def level(cs: Dict[Tuple[str, str], Cell], p: Optional[float] = None) -> str:
    """The DL label, as a summary of the frontier and never as a substitute.

    A level is established when its band holds at a budget no looser than the
    one the level names. The pairing is the measurement: completing trivial
    tasks unattended is not a higher level than needing help on hard ones.
    """
    best = NOT_ESTABLISHED
    for name in LEVEL_ORDER:
        band, loosest = LEVEL_REQ[name]
        limit = budget_index(loosest)
        if any(cs.get((band, h)) is not None and cs[(band, h)].holds(p)
               for h in BUDGETS[:limit + 1]):
            best = name
    return best


def per_family(episodes: Sequence[Episode], tasks: Dict[str, TaskSpec],
               p: Optional[float] = None) -> Dict[str, str]:
    """A DL level per task family, plus ``general`` as the minimum over them.

    One domain must not determine the label. A system at DL4 on software and
    DL2 on research is not DL4; reporting it as DL4 overstates generality,
    which is the same scalar mistake the level scale exists to avoid.
    """
    fams = sorted({e.family for e in episodes})
    out: Dict[str, str] = {}
    for f in fams:
        sub = [e for e in episodes if e.family == f]
        out[f] = level(cells(sub, tasks), p)
    if out:
        rank = {NOT_ESTABLISHED: -1}
        rank.update({n: i for i, n in enumerate(LEVEL_ORDER)})
        out["general"] = min(out.values(), key=lambda v: rank.get(v, -1))
    return out

def ceiling(n: int, z: float = 1.96) -> float:
    """The highest reliability ``n`` flawless attempts can establish.

    A perfect run is not an unlimited claim. With no failures the Wilson lower
    bound is ``n/(n+z^2)``, so six perfect attempts establish 0.61 and nothing
    above it. Printed with the frontier because the first question a blank cell
    raises is whether the system failed or whether the run was too short, and
    those are different findings.
    """
    if n <= 0:
        return 0.0
    return n / (n + z * z)


def attempts_for(p: float, z: float = 1.96) -> int:
    """Flawless attempts needed before ``p`` can be established at all."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0,1)")
    import math as _m
    return int(_m.ceil(p * z * z / (1 - p)))
