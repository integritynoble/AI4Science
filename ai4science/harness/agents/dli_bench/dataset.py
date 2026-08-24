"""Materialising the dataset: instantiate generators at seeds, emit a manifest.

The manifest is the shippable artifact -- a JSONL row per task instance with
its difficulty vector, band, loss terms, required reliability and verifier
note. The instance *contents* are regenerated from the seed rather than
shipped, so the dataset is a few kilobytes and still reproducible byte for
byte.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from .spec import TaskSpec
from .tasks import GENERATORS


def build(root: Path, keys: Sequence[str], seeds: Sequence[int]) -> Dict[str, TaskSpec]:
    """Instantiate every (generator, seed) under ``root``. Returns specs by id."""
    out: Dict[str, TaskSpec] = {}
    for k in keys:
        g = GENERATORS[k]
        for s in seeds:
            spec = g.instantiate(root / k.replace(".", "_") / ("seed%d" % s), s)
            out[spec.task_id] = spec
    return out


def manifest_row(spec: TaskSpec) -> Dict:
    return {
        "task_id": spec.task_id,
        "family": spec.family,
        "level": spec.level,
        "band": spec.difficulty.band,
        "difficulty": spec.difficulty.vector(),
        "seed": spec.seed,
        "deliverables": list(spec.deliverables),
        "answer_key": list(spec.answer_key),
        "pinned_inputs": list(spec.pinned_inputs),
        "loss": {"value": spec.loss.value, "c_detect": spec.loss.c_detect,
                 "c_undo": spec.loss.c_undo, "c_residual": spec.loss.c_residual,
                 "rho": round(spec.loss.rho, 4),
                 "p_star": round(spec.loss.p_star, 4)},
        "permitted_information": list(spec.permitted_information),
        "verifier_note": spec.verifier_note,
        "prompt": spec.prompt,
    }


def write_manifest(specs: Dict[str, TaskSpec], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [manifest_row(s) for s in sorted(specs.values(), key=lambda x: x.task_id)]
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
                    encoding="utf-8")
    return len(rows)
