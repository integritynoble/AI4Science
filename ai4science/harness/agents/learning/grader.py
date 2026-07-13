from __future__ import annotations


def _norm_short(s) -> str:
    return " ".join(str(s).strip().lower().split())


def _numeric_equal(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def grade(quiz: dict, answers: dict) -> dict:
    """Deterministic scoring against the quiz answer key. MCQ = exact option-key
    match; short = normalized-string match or numeric equality. No LLM."""
    questions = quiz.get("questions", [])
    per_question = []
    correct = 0
    for q in questions:
        qid = q.get("id")
        submitted = answers.get(qid)
        key = q.get("answer")
        if q.get("type") == "mcq":
            ok = submitted == key
        else:
            ok = (submitted is not None
                  and (_norm_short(submitted) == _norm_short(key)
                       or _numeric_equal(submitted, key)))
        correct += 1 if ok else 0
        per_question.append({"id": qid, "correct": bool(ok)})
    total = len(questions)
    score = (correct / total) if total else 0.0
    return {"score": score, "correct": correct, "total": total,
            "per_question": per_question}
