from __future__ import annotations
from .grader import grade
from .capability_graph import record_measurement


def grade_and_record(*, quiz: dict, answers: dict, store_path, topic: str,
                     timestamp) -> dict:
    """Examiner operation (owner-invoked): grade the owner's answers and append
    a capability measurement. Deterministic; no agent, no LLM."""
    result = grade(quiz, answers)
    measurement = record_measurement(store_path, topic, result["score"],
                                     result["total"], timestamp)
    return {**measurement, **result}
