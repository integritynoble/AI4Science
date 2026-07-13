from ai4science.harness.agents.learning.grader import grade

QUIZ = {"questions": [
    {"id": "q1", "type": "mcq", "answer": "B"},
    {"id": "q2", "type": "short", "answer": "mitochondria"},
    {"id": "q3", "type": "short", "answer": "42"},
]}

def test_all_correct():
    r = grade(QUIZ, {"q1": "B", "q2": "mitochondria", "q3": "42"})
    assert r["correct"] == 3 and r["total"] == 3 and r["score"] == 1.0

def test_partial_and_normalization():
    r = grade(QUIZ, {"q1": "A", "q2": "  Mitochondria ", "q3": "42.0"})
    # q1 wrong; q2 normalized-correct; q3 numeric-equal
    assert r["correct"] == 2 and abs(r["score"] - 2/3) < 1e-9
    per = {p["id"]: p["correct"] for p in r["per_question"]}
    assert per == {"q1": False, "q2": True, "q3": True}

def test_missing_answer_is_wrong():
    r = grade(QUIZ, {"q1": "B"})
    assert r["correct"] == 1

def test_empty_quiz_scores_zero():
    r = grade({"questions": []}, {})
    assert r["total"] == 0 and r["score"] == 0.0
