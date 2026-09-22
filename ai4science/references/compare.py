"""Compare a new run against a reference: better, worse, or same.

The reference is read-only here, and that is enforced rather than promised: the
seal is verified on the way in and again on the way out, and the comparison is
returned as a new object. An optimiser that could make its reference agree with
it would not be improving.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ai4science.references.store import ReferenceRecord
from ai4science.references.task import FrozenTask

BETTER, WORSE, SAME = "better", "worse", "same"


@dataclass(frozen=True)
class Comparison:
    verdict: str                     # better | worse | same
    reference_id: str
    reference_score: float
    run_score: float
    delta: float
    #: Set when the comparison cannot be trusted even though it produced a
    #: verdict — e.g. the run answered a different task.
    caveat: Optional[str] = None
    detail: Dict[str, Any] = None    # type: ignore[assignment]

    @property
    def trustworthy(self) -> bool:
        return self.caveat is None


def compare(output: str, reference: ReferenceRecord, task: FrozenTask,
            *, run_task_digest: Optional[str] = None) -> Comparison:
    """Grade `output` on `task` and rank it against `reference`.

    `reference` is not modified. Its seal is checked before the comparison and
    again after, so a comparison that somehow mutated it would fail loudly
    instead of quietly succeeding.
    """
    reference.check_seal()
    before = reference.to_dict()

    ref_grade = reference.grade or task.grade(reference.output)
    run_grade = task.grade(output)
    ref_score = float(ref_grade.get("score", 0.0))
    run_score = float(run_grade.get("score", 0.0))

    if run_score > ref_score:
        verdict = BETTER
    elif run_score < ref_score:
        verdict = WORSE
    else:
        verdict = SAME

    caveat = None
    digest = run_task_digest or task.digest
    if digest != reference.task_digest:
        caveat = ("the reference was recorded against task digest %s and this "
                  "run is graded against %s — the task moved, so the ranking "
                  "compares answers to different questions"
                  % (reference.task_digest[:12], digest[:12]))
    elif not run_grade.get("negative_control_passed") and verdict != WORSE:
        caveat = ("the run got the negative control (%s) wrong; a score that "
                  "ties or beats the reference while missing the control is "
                  "not an improvement in this field"
                  % run_grade.get("negative_control"))

    reference.check_seal()
    if reference.to_dict() != before:
        raise AssertionError("the reference was modified during comparison")

    return Comparison(
        verdict=verdict,
        reference_id=reference.record_id,
        reference_score=ref_score,
        run_score=run_score,
        delta=round(run_score - ref_score, 6),
        caveat=caveat,
        detail={"reference_grade": ref_grade, "run_grade": run_grade,
                "reference_model_revision": reference.model_revision,
                "reference_status": reference.status},
    )
