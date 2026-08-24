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
    "DL4": "NOT BUILT -- needs a long-horizon environment with injected failures "
           "and a resource budget; see docs, section 'What is not built'",
    "DL5": "built -- 1 generator, sealed mechanism scored by extrapolation",
    "DL6": "NOT BUILT -- needs a dynamic sandbox in which priorities change "
           "during the run; a static task cannot pose a mission",
    "DLOmega": "NOT BUILT -- needs a charter world with a hidden opportunity "
               "structure and repeated mission cycles",
}


def by_level(level: str) -> Tuple[Generator, ...]:
    return tuple(g for g in GENERATORS.values() if g.level == level)


def by_family(family: str) -> Tuple[Generator, ...]:
    return tuple(g for g in GENERATORS.values() if g.family == family)


def missing_levels() -> Tuple[str, ...]:
    return tuple(k for k, v in COVERAGE.items() if v.startswith("NOT BUILT"))
