from ai4science.harness.agents.learning.rsi_search import (
    score_floor, run_learning_rsi_search, _gate,
)
from ai4science.harness.agents.learning.bench import (
    TRAIN_CASES, VAL_CASES, INCUMBENT_MIN_QUESTIONS,
)


def test_incumbent_accepts_the_inadequate_thin_quiz():
    # default floor (1) wrongly accepts the 1-question quiz
    s = score_floor(INCUMBENT_MIN_QUESTIONS, TRAIN_CASES)
    assert s["accuracy"] < 1.0
    assert s["safety_ok"] is True     # but never accepts an ungrounded quiz


def test_search_finds_floor_and_adopts():
    out = run_learning_rsi_search()
    assert out["best_min_questions"] == 2
    assert out["safety_ok"] is True
    assert out["val_accuracy"] > out["incumbent_val_accuracy"]
    assert out["adopt"] is True


def test_grounding_safety_is_floor_independent():
    # the ungrounded quiz is rejected at EVERY min_questions value
    fab = next(c for c in TRAIN_CASES if c["kind"] == "fabricated")
    for k in (1, 2, 3, 5):
        assert _gate(fab, k) is False


def test_valid_quizzes_stay_accepted_at_the_optimum():
    out = run_learning_rsi_search()
    k = out["best_min_questions"]
    for c in VAL_CASES:
        if c["expected_ok"]:
            assert _gate(c, k) is True, c["name"]


def test_search_is_deterministic():
    a = run_learning_rsi_search()
    b = run_learning_rsi_search()
    assert a["best_min_questions"] == b["best_min_questions"]
    assert a["val_accuracy"] == b["val_accuracy"] and a["adopt"] == b["adopt"]
