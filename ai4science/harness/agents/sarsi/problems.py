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
    #: Does THIS MACHINE have evidence for it — a repository, a benchmark it
    #: has run, a failure it recorded — or is it a reading of the field?
    #:
    #: Computational imaging's first problem is a bug in this repository's own
    #: history. The other fields' lists are read, not measured, and a list that
    #: did not say which was which would be an assertion in the shape of a
    #: measurement — the one thing this system spends its design avoiding.
    grounded: bool = False
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
    #: What is solved TODAY, which stops changing. The walk below marks each
    #: pick solved as it goes — that is how it finds the next frontier — so
    #: reading readiness off `solved` would call every problem in the list
    #: "ready now". The walk's now is not the reader's now, and the reader is
    #: the one being told.
    today = set(solved)
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
        # A tie is separated alphabetically, which is arbitrary. Said out loud,
        # because printing the same reason at two different positions would
        # have a reader mistake position for judgement — and this list is meant
        # to be arguable rather than authoritative.
        tied = [q.id for q in here
                if q.id != pick.id and unblocks(listing, q.id) == n]
        waits_for = [d for d in pick.depends_on if d not in today]
        when = ("ready now" if not waits_for
                else "ready after " + ", ".join(waits_for))
        pick.why = (f"{when}, and unblocks {n} problem(s) below it"
                    if n else f"{when}, and unblocks nothing further")
        if tied:
            pick.why += (f" — tied with {', '.join(sorted(tied))}, so the order "
                         f"between them is arbitrary")
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

def for_field(field: str) -> List[Problem]:
    """The problem list for a field, or `[]` when nobody has written one.

    Empty is not "this field has nothing to solve" — it is "nobody here has
    written down what it is trying to solve", and the caller says which.
    """
    return list(FIELDS.get(field, []))


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
    # ── the hardware half ─────────────────────────────────────────────
    #
    # The five problems above are the ALGORITHM ladder, and on their own they
    # treat the coding optic as a constant. Computational imaging is co-design:
    # the mask, aperture and illumination are design variables, and a solution
    # scored on an arbitrarily chosen optic is a solution to an arbitrarily
    # chosen problem.
    Problem(
        id="hardware-model", tier="L2", depends_on=["forward-model"],
        title="the coding optic as a design variable, with its tolerances",
        verified_when=("the spec states the optic's parameters and the "
                       "tolerance on each, and two masks differing only within "
                       "tolerance give results within the benchmark's noise"),
        because=("this machine has the evidence: the binary-vs-continuous mask "
                 "question moved HDNet 35→28 dB, and the mask IS the coding "
                 "optic — so 'which mask' is a hardware statement wearing an "
                 "implementation detail's clothes")),
    Problem(
        id="built-vs-simulated", tier="L3",
        depends_on=["hardware-model", "benchmark"],
        title="does the fabricated optic match the one that was designed",
        verified_when=("the measured point-spread function of the built optic "
                       "against the simulated one, on the benchmark's metric"),
        because=("a mask optimised in simulation and then fabricated does not "
                 "match, and every downstream number inherits the difference. "
                 "This is the one problem in this field that needs a body — "
                 "see the embodied member of the group")),
    Problem(
        id="co-design", tier="L4",
        depends_on=["built-vs-simulated", "baselines"],
        title="optimise the optic and the reconstruction together",
        verified_when=("a jointly designed system that beats the best "
                       "algorithm-only result on the fixed benchmark, with the "
                       "optic's tolerances respected"),
        because=("the field's actual claim: that designing the measurement and "
                 "the inversion together beats designing either alone")),
    Problem(
        id="principle", tier="L1", depends_on=["solution", "co-design"],
        title="the principle behind why it wins",
        verified_when=("it predicts a result on data the solution was not "
                       "tuned on"),
        because=("promoted last, because a principle inferred from one win is "
                 "a story — and now it has to explain the hardware half too")),
]
for _p in COMPUTATIONAL_IMAGING:
    # Anchored in work this repository has done — the forward-model bug and the
    # mask finding are both in its history.
    _p.grounded = True
for _p in COMPUTATIONAL_IMAGING:
    if _p.id in ("built-vs-simulated", "co-design"):
        # No optic has been fabricated here and nothing has been jointly
        # optimised. These two are read, and the listing says so.
        _p.grounded = False


#: ── the fields below are READ, not measured ──────────────────────────
#:
#: I know computational imaging from this machine's own evidence. These three I
#: know from the literature and from what each agent declares it can do, and
#: saying otherwise would be the failure this whole system is built against.
#: They are useful for AIMING an agent and are not a substitute for someone who
#: works in the field. Each problem carries `grounded=False` and the listing
#: says so.

CANCER: List[Problem] = [
    Problem(
        id="variant-truth-set", tier="L3",
        title="a somatic-variant truth set the classifier is scored against",
        verified_when=("a named cohort with expert-adjudicated calls, and a "
                       "classifier's agreement reported per variant class"),
        because=("classification accuracy quoted without a truth set is "
                 "accuracy against whatever was convenient")),
    Problem(
        id="driver-vs-passenger", tier="L2", depends_on=["variant-truth-set"],
        title="separate driver from passenger, per tumour type",
        verified_when=("recall on known drivers, at a stated false-positive "
                       "rate, for each tumour type rather than pooled"),
        because=("pooled across tumour types it hides that the answer differs "
                 "per type, which is the part that matters clinically")),
    Problem(
        id="pathway-effect", tier="L3", depends_on=["driver-vs-passenger"],
        title="map a driver to the pathway it actually perturbs",
        verified_when=("a prediction that matches a perturbation experiment "
                       "the model was not fitted on"),
        because="a compendium lookup is a citation, not a prediction"),
    Problem(
        id="trial-match", tier="L4", depends_on=["pathway-effect"],
        title="match a variant profile to trials it is actually eligible for",
        verified_when=("eligibility decisions checked against the trial's own "
                       "criteria by someone who can read them"),
        because=("this is the tier where being wrong reaches a person, so it "
                 "sits last and needs the human check named in its criterion")),
]

DRUG_DESIGN: List[Problem] = [
    Problem(
        id="docking-baseline", tier="L3",
        title="a docking benchmark with a decoy set that is not trivially separable",
        verified_when=("enrichment reported against a decoy set matched on "
                       "physicochemical properties, not a random one"),
        because=("a random decoy set makes every scoring function look good, "
                 "which is why the field's older numbers do not transfer")),
    Problem(
        id="pose-vs-score", tier="L2", depends_on=["docking-baseline"],
        title="separate getting the pose right from ranking the ligand right",
        verified_when=("pose RMSD and ranking enrichment reported apart, "
                       "never as one score"),
        because=("a method can rank well while posing badly; one number hides "
                 "which, and the two are fixed differently")),
    Problem(
        id="admet-transfer", tier="L3", depends_on=["docking-baseline"],
        title="ADMET prediction that holds on a scaffold it has not seen",
        verified_when=("held-out performance on a scaffold split, beside the "
                       "random split, with both reported"),
        because=("a random split leaks scaffolds between train and test, so "
                 "the number measures memorisation")),
    Problem(
        id="lead-opt", tier="L4", depends_on=["pose-vs-score", "admet-transfer"],
        title="an optimisation loop that improves potency without breaking ADMET",
        verified_when=("a series where potency improves and the ADMET "
                       "predictions hold on a scaffold split"),
        because="the first place the two halves have to be true at once"),
]

LOW_DOSE_CT: List[Problem] = [
    Problem(
        id="data-records", tier="L3", grounded=True,
        title="a loader and data record anyone can reproduce the inputs from",
        verified_when=("the loader reads the public cohort and reports counts "
                       "and geometry that match the data record"),
        because=("this machine has that work — the WS-1 loader and the "
                 "data-records-first reframe — so it is the one problem here "
                 "grounded in evidence rather than reading")),
    Problem(
        id="dose-ground-truth", tier="L2", depends_on=["data-records"],
        title="what 'low dose' is measured against, per scanner",
        verified_when=("a stated dose reduction factor and the full-dose "
                       "reference it is relative to, per scanner model"),
        because=("a denoising result without the dose it started from is a "
                 "picture, not a measurement")),
    Problem(
        id="task-metric", tier="L3", depends_on=["dose-ground-truth"],
        title="a metric tied to the diagnostic task, not to pixel distance",
        verified_when=("detection or characterisation performance on a named "
                       "task, beside PSNR/SSIM rather than instead of them"),
        because=("PSNR rewards smoothing, and smoothing removes the lesion — "
                 "the metric and the purpose point opposite ways")),
    Problem(
        id="method", tier="L4", depends_on=["task-metric"],
        title="a reconstruction that wins on the task metric",
        verified_when="it beats the baselines on the task metric, not only PSNR",
        because="the first checkable claim the field can make about usefulness"),
]

FIELDS = {
    "computational-imaging": COMPUTATIONAL_IMAGING,
    "cancer": CANCER,
    "drug-design": DRUG_DESIGN,
    "low-dose-ct": LOW_DOSE_CT,
}
