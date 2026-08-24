"""How a task generator is declared, and how one is built into a workspace."""
from __future__ import annotations

import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Tuple

from ..spec import Difficulty, Loss, TaskSpec
from ..verify import Verdict


@dataclass(frozen=True)
class Generator:
    """One problem shape, instantiable at many seeds.

    The benchmark is generated rather than shipped, so a run is reproducible
    from a seed and a frozen system cannot have been tuned on the instance it
    is certified against. ``usable_seeds`` is empty when every seed gives a
    genuinely different instance; where the seed maps into a finite corpus and
    repeats, declare them, or a certification run will validate on its own
    development set.
    """

    key: str
    family: str            # software | data | research | document | tools | planning
    level: str             # the DL level this task is evidence for
    difficulty: Difficulty
    loss: Loss
    prompt: str
    deliverables: Tuple[str, ...]
    verifier_note: str
    build: Callable[[Path, Path, random.Random], None]
    verify: Callable[[Path, Path], Verdict]
    permitted_information: Tuple[str, ...] = ()
    usable_seeds: Tuple[int, ...] = ()

    def instantiate(self, root: Path, seed: int) -> TaskSpec:
        """Create ``root/work`` (staged) and ``root/keyed`` (never staged)."""
        if self.usable_seeds and seed not in self.usable_seeds:
            raise ValueError(
                "%s: seed %d repeats an earlier instance. Usable seeds are %s."
                % (self.key, seed, list(self.usable_seeds)))
        work, keyed = root / "work", root / "keyed"
        for d in (work, keyed):
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True)
        self.build(work, keyed, random.Random(seed))

        # Keyed files split in two. A file the agent also has is a pinned input
        # -- kept here so scoring reads a copy the agent could not have edited.
        # Everything else is the answer, and must never be staged.
        answer, pinned = [], []
        for p in sorted(keyed.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(keyed).as_posix()
            twin = work / rel
            if twin.exists():
                if twin.read_bytes() != p.read_bytes():
                    raise RuntimeError(
                        "%s: %s differs between the staged and pinned copies at "
                        "build time; a pinned input must start identical or the "
                        "score is against a different problem" % (self.key, rel))
                pinned.append(rel)
            else:
                answer.append(rel)

        return TaskSpec(
            task_id="%s#%d" % (self.key, seed),
            family=self.family,
            level=self.level,
            difficulty=self.difficulty,
            prompt=self.prompt,
            loss=self.loss,
            deliverables=self.deliverables,
            answer_key=tuple(answer),
            pinned_inputs=tuple(pinned),
            permitted_information=self.permitted_information,
            verifier_note=self.verifier_note,
            seed=seed,
        )
