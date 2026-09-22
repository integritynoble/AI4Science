"""Scorers run *inside* the evaluator child: no network, no agent tools.

A scorer is ``fn(handoff_root: Path, criteria: dict) -> dict`` returning
``{"decision": "pass"|"fail"|"needs_review", "score": float, "feedback": dict}``.
It must be a pure function of the snapshot and the criteria, or the determinism
check in :mod:`..isolated_eval.runner` will flag its own evaluator.
"""

from __future__ import annotations

from pathlib import Path


def required_artifacts(handoff_root: Path, criteria: dict) -> dict:
    """The default: did the run leave the artefacts its contract promised?"""
    root = Path(handoff_root)
    present = sorted(p.relative_to(root).as_posix()
                     for p in root.rglob("*") if p.is_file())
    wanted = list(criteria.get("required_artifacts", []))
    forbidden = list(criteria.get("forbidden_artifacts", []))

    missing = [a for a in wanted if a not in present]
    offending = [a for a in forbidden if a in present]
    score = 0.0 if not wanted else (len(wanted) - len(missing)) / len(wanted)
    decision = "pass" if not missing and not offending else "fail"
    return {"decision": decision, "score": score,
            "feedback": {"missing": missing, "forbidden_present": offending,
                         "artefacts": present}}
