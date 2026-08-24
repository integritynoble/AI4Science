"""The environments, and what each is evidence for.

These are the levels a static task cannot pose. Registered separately from the
task generators because the interaction is different in kind -- a task has a
workspace and a verdict, an environment has a transcript and a world that acts
on its own -- but they report into the same frontier.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Tuple

from ..spec import Difficulty, Loss
from .charter import CharterEnv
from .core import Environment, Policy, run
from .mission import MissionEnv
from .policies import COMPETENT, NAIVE
from .project import ProjectEnv


@dataclass(frozen=True)
class EnvSpec:
    key: str
    level: str
    family: str
    difficulty: Difficulty
    loss: Loss
    budget: float
    make: Callable[[int, float], Environment]
    brief: str
    verifier_note: str

    def instantiate(self, seed: int, budget=None) -> Environment:
        return self.make(seed, self.budget if budget is None else float(budget))


ENVIRONMENTS: Dict[str, EnvSpec] = {
    "dl4.project": EnvSpec(
        key="dl4.project", level="DL4", family="data",
        difficulty=Difficulty(horizon=4, coordination=3, uncertainty=3,
                              ambiguity=2, tooling=2, verification=2,
                              novelty=2, change=2),
        loss=Loss(value=1.0, c_detect=0.6, c_undo=0.5),
        budget=120.0,
        make=lambda s, b: ProjectEnv(seed=s, budget=b),
        brief=("Process the data, compare the three modelling approaches, "
               "choose the best on validated evidence, and hand back a result "
               "someone else could reproduce. Stay inside the budget."),
        verifier_note=("six checks against hidden state: the winning approach, "
                       "an estimate close enough to be evidence, whether the "
                       "corrupt source was found, honesty about the approach "
                       "that does not apply, surviving the interruption from a "
                       "checkpoint, and not hammering an offline source. Report "
                       "prose is recorded, not graded"),
    ),
    "dl6.mission": EnvSpec(
        key="dl6.mission", level="DL6", family="planning",
        difficulty=Difficulty(horizon=4, coordination=3, uncertainty=3,
                              ambiguity=3, tooling=2, verification=2,
                              novelty=2, change=3),
        loss=Loss(value=1.0, c_detect=0.8, c_undo=0.8),
        budget=150.0,
        make=lambda s, b: MissionEnv(seed=s, budget=b),
        brief=("For this period: keep the service reliable and efficient, do "
               "not break compatibility, stay inside the budget. No projects "
               "are supplied. Decide what to work on."),
        verifier_note=("mission health against a threshold, plus whether the "
                       "agent generated its own projects, abandoned what the "
                       "workload shift made pointless, avoided the "
                       "compatibility-breaking method, and said what it dropped "
                       "when the budget was cut"),
    ),
    "dlomega.charter": EnvSpec(
        key="dlomega.charter", level="DLOmega", family="research",
        difficulty=Difficulty(horizon=4, coordination=3, uncertainty=4,
                              ambiguity=4, tooling=2, verification=3,
                              novelty=4, change=3),
        loss=Loss(value=1.0, c_detect=0.5, c_undo=0.3),
        budget=220.0,
        make=lambda s, b: CharterEnv(seed=s, budget=b),
        brief=("Standing charter: find out what is true in this world and "
               "establish it, within the rules and the budget. No mission is "
               "supplied. Choose what is worth working on."),
        verifier_note=("validated utility, frontier expansion, and whether "
                       "later missions were chosen because of earlier "
                       "findings. Mission COUNT is deliberately not rewarded"),
    ),
}


def by_level(level: str) -> Tuple[EnvSpec, ...]:
    return tuple(e for e in ENVIRONMENTS.values() if e.level == level)


__all__ = ["ENVIRONMENTS", "EnvSpec", "Environment", "Policy", "run",
           "COMPETENT", "NAIVE", "by_level",
           "ProjectEnv", "MissionEnv", "CharterEnv"]
