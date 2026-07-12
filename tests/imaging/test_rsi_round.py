from ai4science.harness.agents.imaging.rsi import run_rsi_round, config_id, DEFAULT_GRID
from collections import defaultdict


def test_config_id_stable():
    assert config_id({"iters": 160, "tv_weight": 0.01}) == "iters160_tv0.01"


def test_round_ranks_by_cp_scores(tmp_path):
    # a stub client that: opens runs, accepts stage_heldout/stage_input/sandbox_execute,
    # and returns a FIXED psnr per candidate version from score_heldout (higher for iters160_tv0.01),
    # records register_version calls, records all stage_heldout and score_heldout calls for coverage verification,
    # and returns eval_ref from evaluate_candidates.
    class Stub:
        def __init__(self):
            self.registered = []
            self.score_heldout_calls = []  # List of (run_id, scene_id, version) tuples
            self.stage_heldout_calls = []  # List of (run_id, scene_id) tuples

        def open_run(self, *a, **k):
            return {"run_id": "R", "workspace_path": str(tmp_path/"ws"),
                    "capability_profile": "A1", "limits": {}}

        def stage_input(self, *a, **k):
            return {"ok": True}

        def stage_heldout(self, run_id, scene_id, *a, **k):
            self.stage_heldout_calls.append((run_id, scene_id))
            return {"ok": True}

        def sandbox_execute(self, *a, **k):
            return {"is_error": False, "exit_code": 0, "artifacts": []}

        def score_heldout(self, run_id, scene_id, version=None):
            # Record the call for coverage verification
            self.score_heldout_calls.append((run_id, scene_id, version))
            # Return per-version PSNR (higher for iters160_tv0.01 for deterministic ranking)
            return {"psnr": 30.0 if version == "iters160_tv0.01" else 20.0}

        def register_version(self, *a, **k):
            self.registered.append(a)
            return {"ok": True}

        def evaluate_candidates(self, run_id, results):
            return {"ok": True, "eval_ref": run_id}

    client = Stub()
    held_out_scene_ids = [0, 1]
    out = run_rsi_round(client=client, held_out_scene_ids=held_out_scene_ids, seed_solver_ws=tmp_path / "seed")

    # Existing assertions: best config ranked first, eval_ref returned, each candidate registered
    assert out["ranked"][0][0] == "iters160_tv0.01"      # best CP score ranked first
    assert out["eval_ref"] == "R"
    assert len(client.registered) == len(DEFAULT_GRID)   # each candidate registered

    # Full-coverage verification: score_heldout called exactly len(DEFAULT_GRID) * len(held_out_scene_ids) times
    expected_score_calls = len(DEFAULT_GRID) * len(held_out_scene_ids)
    assert len(client.score_heldout_calls) == expected_score_calls, \
        f"Expected {expected_score_calls} score_heldout calls, got {len(client.score_heldout_calls)}"

    # Verify that for EACH candidate (config_id), the set of distinct scene_ids scored equals the full set
    scores_by_version = defaultdict(set)
    for run_id, scene_id, version in client.score_heldout_calls:
        scores_by_version[version].add(scene_id)

    # Each candidate should have scored all held-out scenes
    for cfg in DEFAULT_GRID:
        cfg_id = config_id(cfg)
        assert cfg_id in scores_by_version, f"Candidate {cfg_id} not scored"
        assert scores_by_version[cfg_id] == set(held_out_scene_ids), \
            f"Candidate {cfg_id} scored scenes {scores_by_version[cfg_id]}, expected {set(held_out_scene_ids)}"
