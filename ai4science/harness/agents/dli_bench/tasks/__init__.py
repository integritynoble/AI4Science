"""The task registry.

The dataset is *generated*, not shipped: each generator makes a genuinely
different instance per seed, so a system frozen before certification cannot
have been tuned on the instance that certifies it. That is the anti-gaming rule
made mechanical rather than promised.

What is built, and what is not, is stated in :data:`COVERAGE`. A level with no
runnable task is named as absent rather than left to be inferred from a short
list -- a suite that quietly covers less than its scale is the same failure as
a frontier that quietly omits the classes it could not verify.
"""
from __future__ import annotations

from typing import Dict, Tuple

from . import atomic, multistep, routine, sealed
from .base import Generator

_MODULES = (atomic, routine, multistep, sealed)

GENERATORS: Dict[str, Generator] = {}
for _m in _MODULES:
    for _g in _m.ALL:
        if _g.key in GENERATORS:
            raise RuntimeError("duplicate generator key %r" % _g.key)
        GENERATORS[_g.key] = _g

#: Levels this suite can run today, and what each rests on.
COVERAGE: Dict[str, str] = {
    "DL0": "built -- 5 generators, exact verification",
    "DL1": "built -- 3 generators, exact verification",
    "DL2": "built -- 2 generators, withheld test suites",
    "DL3": "built -- 1 generator, measured against the original in-session",
    "DL4": "built -- 1 environment: long horizon, a corrupt source nobody "
           "names, an outage, a forced interruption, a budget",
    "DL5": "built -- 1 generator, sealed mechanism scored by extrapolation",
    "DL6": "built -- 1 environment: a mission, with priorities that move "
           "during the run and a budget cut partway",
    "DLOmega": "built -- 1 environment: a charter, a hidden opportunity graph "
               "with distractors and unlocks, scored on validated utility",
}

#: Levels posed by an environment rather than a task generator. Kept distinct
#: because the interaction differs in kind: a task has a workspace and a
#: verdict, an environment has a transcript and a world that acts on its own.
ENVIRONMENT_LEVELS: Tuple[str, ...] = ("DL4", "DL6", "DLOmega")


def by_level(level: str) -> Tuple[Generator, ...]:
    return tuple(g for g in GENERATORS.values() if g.level == level)


def by_family(family: str) -> Tuple[Generator, ...]:
    return tuple(g for g in GENERATORS.values() if g.family == family)


def missing_levels() -> Tuple[str, ...]:
    return tuple(k for k, v in COVERAGE.items() if v.startswith("NOT BUILT"))


def posed_by_environment(level: str) -> bool:
    return level in ENVIRONMENT_LEVELS
