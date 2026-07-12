from ai4science.harness.agents.imaging.rsi_search import run_rsi_search, clamp
from ai4science.harness.agents.imaging.rsi import config_id


class FakeClient:
    def __init__(self, lkg=None): self._lkg = lkg
    def get_last_known_good(self, kind, name): return self._lkg


def _round_fn_from(landscape):
    # landscape: dict domain -> (config_id -> psnr). Returns a round_fn that ranks candidates by it.
    def round_fn(*, client, held_out_scene_ids, candidates, seed_solver_ws, domain, **kw):
        table = landscape.get(domain, {})
        ranked = sorted(((config_id(c), table.get(config_id(c))) for c in candidates),
                        key=lambda it: (it[1] is None, -(it[1] or 0.0)))
        return {"ranked": ranked, "eval_ref": f"ref-{domain}"}
    return round_fn


def test_search_converges_to_landscape_peak():
    # search landscape peaks at iters240_tv0.01; val gives everyone the same
    search = {"iters80_tv0.01": 10.0, "iters160_tv0.01": 20.0, "iters240_tv0.01": 30.0,
              "iters320_tv0.01": 25.0, "iters80_tv0.02": 12.0, "iters80_tv0.005": 9.0,
              "iters160_tv0.02": 18.0, "iters160_tv0.005": 17.0, "iters240_tv0.02": 24.0,
              "iters240_tv0.005": 26.0}
    val = {}  # default None → best still returned
    landscape = {"cassi_search": search, "cassi_val": {config_id(clamp({"iters":240,"tv_weight":0.01})): 30.0,
                                                       config_id(clamp({"iters":80,"tv_weight":0.01})): 10.0}}
    out = run_rsi_search(client=FakeClient(), seed_solver_ws="x",
                         search_scene_ids=[0], val_scene_ids=[0],
                         seed_config={"iters": 80, "tv_weight": 0.01},
                         round_fn=_round_fn_from(landscape), max_rounds=6)
    assert out["best_config"]["iters"] == 240
    assert out["val_score"] == 30.0
    assert out["converged"] is True

def test_budget_cap_stops_monotone_landscape():
    # strictly increasing with iters → never "converges", must stop at max_rounds
    def round_fn(*, client, held_out_scene_ids, candidates, seed_solver_ws, domain, **kw):
        ranked = sorted(((config_id(c), float(c["iters"])) for c in candidates),
                        key=lambda it: -it[1])
        return {"ranked": ranked, "eval_ref": f"ref-{domain}"}
    out = run_rsi_search(client=FakeClient(), seed_solver_ws="x",
                         search_scene_ids=[0], val_scene_ids=[0],
                         seed_config={"iters": 80, "tv_weight": 0.01},
                         round_fn=round_fn, max_rounds=3, epsilon=0.25)
    assert out["rounds"] <= 3

def test_validation_scores_best_and_incumbent():
    # incumbent is the last-known-good; validation round must score both
    landscape = {"cassi_search": {"iters160_tv0.01": 30.0, "iters80_tv0.01": 10.0},
                 "cassi_val": {"iters160_tv0.01": 5.0, "iters80_tv0.01": 25.0}}  # val prefers incumbent
    lkg = {"version": "iters80_tv0.01", "metadata": {"iters": 80, "tv_weight": 0.01}}
    out = run_rsi_search(client=FakeClient(lkg=lkg), seed_solver_ws="x",
                         search_scene_ids=[0], val_scene_ids=[0],
                         seed_config={"iters": 160, "tv_weight": 0.01},
                         round_fn=_round_fn_from(landscape), max_rounds=2)
    # search picked iters160 (30 on search), but validation prefers the incumbent iters80
    assert out["val_score"] == 5.0
    assert out["incumbent_val_score"] == 25.0
    assert out["val_score"] <= out["incumbent_val_score"]   # RSI-integrity: would NOT promote
