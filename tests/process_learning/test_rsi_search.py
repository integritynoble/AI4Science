from ai4science.harness.agents.process_learning.rsi_search import (
    score_strictness, run_process_learning_rsi_search,
)
from ai4science.harness.agents.process_learning.bench import (
    TRAIN_CASES, VAL_CASES, INCUMBENT_MIN_CLAIM,
)


def test_incumbent_falsely_rejects_a_valid_transition():
    # the shipped strictness (6) rejects the valid 6-word uncited transition
    s = score_strictness(INCUMBENT_MIN_CLAIM, TRAIN_CASES)
    assert s["safety_ok"] is True          # but never accepts a fabrication
    assert s["autonomy"] < 1.0             # ...at the cost of a false rejection


def test_search_finds_the_safe_optimum_and_adopts():
    out = run_process_learning_rsi_search()
    assert out["best_min_claim_words"] == 7        # unique safe optimum
    assert out["safety_ok"] is True
    assert out["val_autonomy"] > out["incumbent_val_autonomy"]
    assert out["val_accuracy"] >= out["incumbent_val_accuracy"]
    assert out["adopt"] is True


def test_a_looser_threshold_would_break_safety():
    # threshold 8 accepts the 7-word uncited fabricated claim -> unsafe, so the
    # search must NOT pick it.
    s8 = score_strictness(8, TRAIN_CASES)
    assert s8["safety_ok"] is False and s8["accepted_fabricated"] > 0
    assert run_process_learning_rsi_search()["best_min_claim_words"] != 8


def test_nonverbatim_citation_rejected_at_every_threshold():
    # the grounding floor is threshold-independent: the non-verbatim case is
    # rejected whether strict or loose.
    from ai4science.harness.agents.process_learning.rsi_search import _gate
    fab = next(c for c in TRAIN_CASES if c["name"] == "f_nonverbatim")
    for k in (3, 6, 7, 12, 15):
        assert _gate(fab, k) is False


def test_search_is_deterministic():
    a = run_process_learning_rsi_search()
    b = run_process_learning_rsi_search()
    assert a["best_min_claim_words"] == b["best_min_claim_words"]
    assert a["val_accuracy"] == b["val_accuracy"] and a["adopt"] == b["adopt"]
