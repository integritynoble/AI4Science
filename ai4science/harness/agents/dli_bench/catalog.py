"""The task catalogue, and which of its cards can actually be run.

Two halves of a benchmark were written independently.

**The catalogue** (`dataset/catalog_v0_1.jsonl`) is the specification: 96 task
cards covering all eight levels and six families, each with its intervention
budget, escalation policy, CID ceiling, reliability target, time budget and
split. It is complete across the scale and, by its own admission, has no
runnable assets --

    asset_bundle_status: "specification starter; executable assets should be
                          generated from the seed and kept hidden for
                          certification"

**The generators** (:mod:`.tasks`) are the other half: instances that build
themselves from a seed, with withheld keys and verifiers that have been shown
to pass a correct solution as well as refuse an empty one. They run, and they
cover five of the eight levels.

This module joins them, so that the catalogue's blanket status line becomes a
per-card fact: *this* card is executable, *that* one is a specification. A
benchmark that reports 96 tasks and runs 12 of them should say which 12, and
the difference between a card and a runnable instance is the difference between
a plan and a measurement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .spec import COORDINATES, Difficulty
from .tasks import COVERAGE, GENERATORS

CATALOG = Path(__file__).parent / "dataset" / "catalog_v0_1.jsonl"

#: Family names differ between the two halves. Only one actually disagrees.
FAMILY_ALIAS: Dict[str, str] = {
    "tool_use": "tools",
    "software": "software",
    "data": "data",
    "research": "research",
    "planning": "planning",
    "document": "document",
}

#: Catalogue difficulty keys -> the coordinate names used here.
_COORD_KEY = {
    "horizon": "difficulty_horizon",
    "coordination": "difficulty_coordination",
    "uncertainty": "difficulty_uncertainty",
    "ambiguity": "difficulty_ambiguity",
    "tooling": "difficulty_tool_diversity",
    "verification": "difficulty_verification",
    "novelty": "difficulty_novelty",
    "change": "difficulty_env_change",
}


@dataclass(frozen=True)
class Card:
    """One specified task, and whether anything can run it."""

    task_id: str
    level: str
    band: str
    family: str
    title: str
    prompt: str
    budget: str
    max_cid: str
    reliability_target: float
    split: str
    verifier_type: str
    hidden_perturbation: str
    min_actions: int
    dynamic_environment: bool
    difficulty: Dict[str, int]
    raw: Dict

    @property
    def declared_band(self) -> str:
        """The band this card's own difficulty vector implies.

        The catalogue rates 0--5 and this suite 0--4, so the vector is
        **rescaled** rather than clamped. That is not a cosmetic choice: clamping
        left 54 of 84 cards banding somewhere other than they claim, with the
        errors piled on the high side (+1 on 24, +2 on 18). Rescaling leaves 24,
        centred on zero. The disagreement was mostly a scale, and reading it as
        a disagreement about difficulty would have been wrong.

        The 24 that remain are the real calibration work.
        """
        v = {k: min(4, max(0, round(int(self.difficulty.get(k, 0)) * 4 / 5)))
             for k in COORDINATES}
        return Difficulty(**v).band


def load(path: Path = CATALOG) -> List[Card]:
    out: List[Card] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out.append(Card(
            task_id=r["task_id"],
            level=r["target_dl"].replace("Ω", "Omega"),
            band=r["task_band"].replace("\u03a9", "Omega"),
            family=FAMILY_ALIAS.get(r["family"], r["family"]),
            title=r.get("task_title", ""),
            prompt=r.get("delegation_prompt", ""),
            budget=r.get("primary_intervention_budget", ""),
            max_cid=str(r.get("max_cid", "")),
            reliability_target=float(r.get("reliability_target", 0.0)),
            split=r.get("split", ""),
            verifier_type=r.get("verifier_type", ""),
            hidden_perturbation=r.get("hidden_perturbation", "None"),
            min_actions=int(r.get("min_meaningful_actions", 0)),
            dynamic_environment=str(r.get("dynamic_environment", "No")).lower().startswith("y"),
            difficulty={k: int(r.get(v, 0)) for k, v in _COORD_KEY.items()},
            raw=r,
        ))
    return out


def executable_for(card: Card) -> Tuple[str, ...]:
    """What can pose this card: same level, same family.

    Either a task generator or an environment. The upper levels are posed by
    environments and the lower ones by generators, and a card does not care
    which -- it cares whether anything can run it.
    """
    from .envs import ENVIRONMENTS
    out = [k for k, g in GENERATORS.items()
           if g.level == card.level and g.family == card.family]
    out += [k for k, e in ENVIRONMENTS.items()
            if e.level == card.level and e.family == card.family]
    return tuple(sorted(out))


def crosswalk(cards: Optional[Sequence[Card]] = None) -> Dict[str, Tuple[str, ...]]:
    cards = list(cards if cards is not None else load())
    return {c.task_id: executable_for(c) for c in cards}


def coverage_report(cards: Optional[Sequence[Card]] = None) -> str:
    cards = list(cards if cards is not None else load())
    xw = crosswalk(cards)
    runnable = [c for c in cards if xw[c.task_id]]
    spec_only = [c for c in cards if not xw[c.task_id]]

    by_level: Dict[str, List[int]] = {}
    for c in cards:
        s = by_level.setdefault(c.level, [0, 0])
        s[0] += 1
        if xw[c.task_id]:
            s[1] += 1

    L = ["DLI-Bench catalogue coverage", "=" * 27, "",
         "cards specified: %d" % len(cards),
         "cards a generator can pose: %d" % len(runnable),
         "cards that are specification only: %d" % len(spec_only), "",
         "%-10s %8s %10s   %s" % ("level", "cards", "runnable", "what is missing"),
         "-" * 78]
    order = ["DL0", "DL1", "DL2", "DL3", "DL4", "DL5", "DL6", "DLOmega"]
    for lvl in order:
        if lvl not in by_level:
            continue
        total, run = by_level[lvl]
        gap = ""
        if run != total:
            fams = sorted({c.family for c in cards
                           if c.level == lvl and not xw[c.task_id]})
            gap = "nothing poses: %s" % ", ".join(fams)
        L.append("%-10s %8d %10d   %s" % (lvl, total, run, gap[:44]))

    L += ["", "families with no executable generator at any level:"]
    from .envs import ENVIRONMENTS as _E
    fams_run = {g.family for g in GENERATORS.values()} | {e.family for e in _E.values()}
    fams_all = {c.family for c in cards}
    L.append("  " + (", ".join(sorted(fams_all - fams_run)) or "none"))

    mismatched = [c for c in cards if c.declared_band != c.band]
    L += ["", "cards whose difficulty vector does not band where they claim: %d of %d"
          % (len(mismatched), len(cards))]
    if mismatched:
        L.append("  (the catalogue rates 0-5, this suite 0-4, so the vector is")
        L.append("   rescaled before banding. Clamping instead would leave 54 --")
        L.append("   most of the gap was a scale, not a disagreement about")
        L.append("   difficulty. What is left is the calibration work.)")
        for c in mismatched[:6]:
            L.append("    %-18s claims %-3s vector bands %s" % (c.task_id, c.band, c.declared_band))
        if len(mismatched) > 6:
            L.append("    ... and %d more" % (len(mismatched) - 6))

    splits: Dict[str, int] = {}
    for c in cards:
        splits[c.split] = splits.get(c.split, 0) + 1
    L += ["", "splits: " + ", ".join("%s=%d" % kv for kv in sorted(splits.items())),
          "",
          "The certification split must stay sealed. A card whose assets are",
          "generated from a published seed is only hidden while the seed is.",
          ]
    return "\n".join(L)
