"""`PRB` — the field's open problems, in the order they have to be solved.

    Solve what unblocks the most tiers below it, among the things that can be
    verified now.

Two clauses, and the order they are applied in is the whole design:

  * **"can be verified now" is a FILTER**, not a tiebreak. A problem whose
    dependencies are unsolved cannot be checked, so it is not a candidate
    however much it would unblock. Ranking by unblocking first and readiness
    second would put the most valuable *unverifiable* thing at the top of the
    list, and that is where a field goes to argue instead of measure.
  * **"unblocks the most" ranks what is left**, counted transitively: a problem
    that unblocks one problem which unblocks four has unblocked five.

The list is **computed, never sorted by hand.** A hand-ordered list is one
person's judgement wearing an algorithm's clothes, and nobody can later tell
whether it changed because the field moved or because somebody edited it.

Three things are refused rather than ordered anyway — a cycle, a dependency
that is not in the list, and a duplicate id. An order produced from any of them
is an arbitrary one with an algorithm's authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

#: The four tiers, coarsest first. Present for reporting — the ORDER comes from
#: the dependency graph, not from the tier, because a field's principle is
#: often the last thing verifiable rather than the first.
TIERS = ("L1", "L2", "L3", "L4")


class Unorderable(Exception):
    """The list cannot be ordered, and this says what is wrong with it."""


@dataclass
class Problem:
    id: str
    tier: str
    title: str
    #: ids that must be SOLVED before this can be checked at all
    depends_on: List[str] = field(default_factory=list)
    solved: bool = False
    #: can it be checked with what exists today? A principle nobody can test
    #: yet unblocks nothing, because every tier under it inherits the doubt.
    verifiable: bool = True
    #: what solving it would mean, in the shape a verifier can read
    verified_when: str = ""
    #: why it sits where it does, in the field's own terms
    because: str = ""
    #: filled by `order`
    why: str = ""


def _check(listing: Sequence[Problem]) -> Dict[str, Problem]:
    by_id: Dict[str, Problem] = {}
    for p in listing:
        if p.id in by_id:
            raise Unorderable(
                f"{p.id!r} appears twice — ids key the dependency graph, and "
                f"two problems with one id is two answers to 'is it solved'")
        by_id[p.id] = p
    for p in listing:
        for dep in p.depends_on:
            if dep not in by_id:
                raise Unorderable(
                    f"{p.id!r} depends on {dep!r}, which is not in this list — "
                    f"a ghost dependency is a problem nobody can see and "
                    f"nobody can solve")
    _no_cycles(by_id)
    return by_id


def _no_cycles(by_id: Dict[str, Problem]) -> None:
    seen: Set[str] = set()
    stack: Set[str] = set()

    def walk(pid: str, path: List[str]) -> None:
        if pid in stack:
            raise Unorderable(
                f"there is a cycle: {' → '.join(path + [pid])}. An order "
                f"produced from a cycle is an arbitrary one with an "
                f"algorithm's authority")
        if pid in seen:
            return
        stack.add(pid)
        for dep in by_id[pid].depends_on:
            walk(dep, path + [pid])
        stack.discard(pid)
        seen.add(pid)

    for pid in by_id:
        walk(pid, [])


def unblocks(listing: Sequence[Problem], pid: str) -> int:
    """How many problems this one stands in front of, transitively.

    One that unblocks a problem which unblocks four has unblocked five — the
    count is of everything downstream, because that is what "unblocks the most
    tiers below it" means.
    """
    by_id = _check(listing)
    if pid not in by_id:
        raise Unorderable(f"{pid!r} is not in this list")
    direct: Dict[str, List[str]] = {k: [] for k in by_id}
    for p in listing:
        for dep in p.depends_on:
            direct[dep].append(p.id)
    out: Set[str] = set()
    stack = list(direct[pid])
    while stack:
        here = stack.pop()
        if here in out:
            continue
        out.add(here)
        stack.extend(direct[here])
    return len(out)


def ready(listing: Sequence[Problem]) -> List[Problem]:
    """The problems that can be checked NOW: unsolved, verifiable, and with
    every dependency already solved."""
    by_id = _check(listing)
    return [p for p in listing
            if not p.solved and p.verifiable
            and all(by_id[d].solved for d in p.depends_on)]


def order(listing: Sequence[Problem]) -> List[Problem]:
    """The whole list, in the order it should be worked.

    Ready problems first, ranked by what they unblock; then the rest, in the
    order they become reachable. Each carries `why` it is where it is — a list
    a reader cannot argue with is one they have to take on faith.
    """
    by_id = _check(listing)
    remaining = [p for p in listing if not p.solved]
    solved: Set[str] = {p.id for p in listing if p.solved}
    out: List[Problem] = []

    while remaining:
        here = [p for p in remaining
                if p.verifiable and all(d in solved for d in p.depends_on)]
        if not here:
            # Nothing is checkable: take what is closest to being so, in
            # dependency order, so the list still says what comes after what.
            here = [p for p in remaining
                    if all(d in solved for d in p.depends_on)] or remaining
            for p in sorted(here, key=lambda q: (-unblocks(listing, q.id), q.id)):
                blockers = [d for d in p.depends_on if d not in solved]
                p.why = ("waiting on " + ", ".join(blockers) if blockers
                         else "nothing can check this yet")
                out.append(p)
                solved.add(p.id)
                remaining.remove(p)
            continue
        pick = sorted(here, key=lambda q: (-unblocks(listing, q.id), q.id))[0]
        n = unblocks(listing, pick.id)
        pick.why = (f"ready now, and unblocks {n} problem(s) below it"
                    if n else "ready now, and unblocks nothing further")
        out.append(pick)
        solved.add(pick.id)
        remaining.remove(pick)

    return out


def next_of(listing: Sequence[Problem]) -> Optional[Problem]:
    """The one to work on. `None` when there is nothing left that can be
    checked — which is a field saying something about itself, not an error."""
    got = order(listing)
    return got[0] if got else None


# ── the field furthest along ──────────────────────────────────────────
#
# Written as data so the ORDER is computed from the rule and can be checked
# against what §11b claims. A hand-sorted list would agree with the document by
# construction and prove nothing.

COMPUTATIONAL_IMAGING: List[Problem] = [
    Problem(
        id="forward-model", tier="L2",
        title="settle the forward model — mask convention, dispersion, normalisation",
        verified_when=("one spec, and two independent implementations of it "
                       "reconstruct the same scene to within 0.1 dB"),
        because=("papers disagree, so every number below this is uncomparable "
                 "until it is settled. The CASSI wrapper bug that cost "
                 "35.5→28 dB was this, one layer down")),
    Problem(
        id="benchmark", tier="L3", depends_on=["forward-model"],
        title="a benchmark that fixes data, mask and metric together",
        verified_when=("a named dataset, a named mask, and a metric with a "
                       "reference value any reader can reproduce"),
        because="a metric on unfixed data measures the data"),
    Problem(
        id="baselines", tier="L3", depends_on=["benchmark"],
        title="re-run the baselines under that benchmark",
        verified_when=("every baseline's number produced on this machine, "
                       "beside the number its paper quoted"),
        because=("a quoted number is a claim about somebody else's forward "
                 "model")),
    Problem(
        id="solution", tier="L4", depends_on=["baselines"],
        title="a method that beats the re-run baselines",
        verified_when="it beats the re-run numbers on the fixed benchmark",
        because="the first checkable 'better' the field has"),
    Problem(
        id="principle", tier="L1", depends_on=["solution"],
        title="the principle behind why it wins",
        verified_when=("it predicts a result on data the solution was not "
                       "tuned on"),
        because=("promoted last, because a principle inferred from one win is "
                 "a story")),
]
