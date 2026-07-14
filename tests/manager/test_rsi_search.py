from ai4science.harness.agents.manager.routing_policy import (
    RoutePolicy, incumbent_route_policy,
)
from ai4science.harness.agents.manager.rsi_search import (
    score_routing, run_manager_rsi_search,
)
from ai4science.harness.agents.manager.bench import SPECS, TRAIN_CASES, VAL_CASES


def test_incumbent_baseline_pinned():
    s = score_routing(incumbent_route_policy(), VAL_CASES)
    assert s["accuracy"] == 0.5      # 5/10 held-out cases routed correctly
    assert s["safety_ok"] is True    # incumbent fabricates no gap recommendation


def test_search_improves_val_and_recommends_adopt():
    out = run_manager_rsi_search()
    assert out["safety_ok"] is True
    assert out["val_accuracy"] > out["incumbent_val_accuracy"]
    assert out["val_coverage"] > out["incumbent_val_coverage"]
    assert out["adopt"] is True
    assert out["val_accuracy"] == 0.9
    learned = out["learned"]
    assert "denoise" in learned.get("imaging", ())
    assert "memorize" in learned.get("learning", ())
    assert "refactor" in learned.get("work", ())


def test_does_not_overfit_to_100_percent():
    # "compress the datacube" shares no train-taught token -> stays a gap
    out = run_manager_rsi_search()
    assert out["val_accuracy"] < 1.0


def test_safety_gaps_never_become_recommendations():
    out = run_manager_rsi_search()
    best = RoutePolicy(out["best_policy"])
    # every expected-gap case still routes to a gap under the learned policy
    for c in TRAIN_CASES + VAL_CASES:
        if c["expected"] is None:
            assert best.route(c["intent"], SPECS)["primary"] is None, c["intent"]
    assert score_routing(best, TRAIN_CASES)["safety_ok"] is True
    assert score_routing(best, VAL_CASES)["safety_ok"] is True


def test_adversarial_candidate_that_breaks_a_gap_is_rejected():
    # a policy that routes an out-of-domain gap to an agent must score safety_ok False
    evil = RoutePolicy({"work": ("flight", "pizza", "hotel", "groceries")})
    s = score_routing(evil, TRAIN_CASES)
    assert s["safety_ok"] is False and s["gap_violations"] > 0


def test_no_regression_on_incumbent_hits():
    out = run_manager_rsi_search()
    best = RoutePolicy(out["best_policy"])
    inc = incumbent_route_policy()
    for c in VAL_CASES:
        if inc.route(c["intent"], SPECS)["primary"] == c["expected"]:
            assert best.route(c["intent"], SPECS)["primary"] == c["expected"], c["intent"]


def test_search_is_deterministic():
    a = run_manager_rsi_search()
    b = run_manager_rsi_search()
    assert a["best_policy"] == b["best_policy"]
    assert a["val_accuracy"] == b["val_accuracy"]
    assert a["adopt"] == b["adopt"]


def test_returns_recommendation_not_action():
    # the loop mutates no shipped spec keywords
    before = {s.name: s.keywords for s in SPECS}
    run_manager_rsi_search()
    after = {s.name: s.keywords for s in SPECS}
    assert before == after
