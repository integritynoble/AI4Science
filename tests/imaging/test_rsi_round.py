from ai4science.harness.agents.imaging.rsi import run_rsi_round, config_id, DEFAULT_GRID


def test_config_id_stable():
    assert config_id({"iters": 160, "tv_weight": 0.01}) == "iters160_tv0.01"


def test_round_ranks_by_cp_scores(tmp_path):
    # a stub client that: opens runs, accepts stage_heldout/stage_input/sandbox_execute,
    # and returns a FIXED psnr per candidate version from score_heldout (higher for iters160_tv0.01),
    # records register_version calls, and returns eval_ref from evaluate_candidates.
    class Stub:
        def __init__(self): self.registered = []
        def open_run(self, *a, **k): return {"run_id": "R", "workspace_path": str(tmp_path/"ws"),
                                             "capability_profile": "A1", "limits": {}}
        def stage_input(self, *a, **k): return {"ok": True}
        def stage_heldout(self, *a, **k): return {"ok": True}
        def sandbox_execute(self, *a, **k): return {"is_error": False, "exit_code": 0, "artifacts": []}
        def score_heldout(self, run_id, scene_id, version=None):
            return {"psnr": 30.0 if version == "iters160_tv0.01" else 20.0}
        def register_version(self, *a, **k): self.registered.append(a); return {"ok": True}
        def evaluate_candidates(self, run_id, results): return {"ok": True, "eval_ref": run_id}
    client = Stub()
    out = run_rsi_round(client=client, held_out_scene_ids=[0, 1], seed_solver_ws=tmp_path / "seed")
    assert out["ranked"][0][0] == "iters160_tv0.01"      # best CP score ranked first
    assert out["eval_ref"] == "R"
    assert len(client.registered) == len(DEFAULT_GRID)   # each candidate registered
