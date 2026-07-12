from ai4science.harness.agents.imaging.rsi_search import (
    CONFIG_BOUNDS, INITIAL_STEP, clamp, CoordinateDescentStrategy)
from ai4science.harness.agents.imaging.rsi import config_id

def test_clamp_bounds_both_axes():
    c = clamp({"iters": 100000, "tv_weight": 5.0})
    assert c["iters"] == CONFIG_BOUNDS["iters"][1]
    assert c["tv_weight"] == CONFIG_BOUNDS["tv_weight"][1]
    c2 = clamp({"iters": 1, "tv_weight": 0.0})
    assert c2["iters"] == CONFIG_BOUNDS["iters"][0]
    assert c2["tv_weight"] == CONFIG_BOUNDS["tv_weight"][0]

def test_propose_neighbors_clamped_and_deduped():
    s = CoordinateDescentStrategy()
    best = {"iters": 160, "tv_weight": 0.01}
    cands = s.propose(history={}, best=best, step=INITIAL_STEP)
    ids = {config_id(c) for c in cands}
    # ± iters step and ×/÷ tv, all distinct and clamped, best itself excluded
    assert config_id(clamp(best)) not in ids
    assert any(c["iters"] == 240 for c in cands)     # 160 + 80
    assert any(c["iters"] == 80 for c in cands)      # 160 - 80
    assert any(abs(c["tv_weight"] - 0.02) < 1e-9 for c in cands)   # 0.01 * 2
    assert any(abs(c["tv_weight"] - 0.005) < 1e-9 for c in cands)  # 0.01 / 2 (clamped floor)
    assert len(cands) == len({config_id(c) for c in cands})        # deduped

def test_propose_skips_already_scored():
    s = CoordinateDescentStrategy()
    best = {"iters": 160, "tv_weight": 0.01}
    all_cands = s.propose(history={}, best=best, step=INITIAL_STEP)
    seen = {config_id(all_cands[0]): 10.0}
    fewer = s.propose(history=seen, best=best, step=INITIAL_STEP)
    assert config_id(all_cands[0]) not in {config_id(c) for c in fewer}

def test_propose_empty_when_all_seen():
    s = CoordinateDescentStrategy()
    best = {"iters": 160, "tv_weight": 0.01}
    cands = s.propose(history={}, best=best, step=INITIAL_STEP)
    seen = {config_id(c): 1.0 for c in cands}
    assert s.propose(history=seen, best=best, step=INITIAL_STEP) == []

def test_shrink_reduces_step():
    s = CoordinateDescentStrategy()
    step2 = s.shrink(INITIAL_STEP)
    assert step2["iters"] < INITIAL_STEP["iters"]
    assert 1.0 < step2["tv_mul"] < INITIAL_STEP["tv_mul"]
    assert step2["iters"] >= 5
