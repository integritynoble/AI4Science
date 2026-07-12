from __future__ import annotations
from pathlib import Path
from .benchmark import seed_cassi_workspace

# Security: answer key must never reach the untrusted sandbox where a compromised solver
# could copy it to results/reconstruction_xhat.npy and pass the reference-free judge.
_NEVER_STAGE = {"data/ground_truth_x.npy"}

DEFAULT_GRID = [
    {"iters": 80, "tv_weight": 0.01},
    {"iters": 160, "tv_weight": 0.01},
    {"iters": 80, "tv_weight": 0.05},
    {"iters": 160, "tv_weight": 0.05},
]


def config_id(cfg: dict) -> str:
    return f"iters{cfg['iters']}_tv{cfg['tv_weight']}"


def _solver_command(iters: int, tv_weight: float) -> list:
    return ["python3", "code/run_solver.py", "--workspace", ".",
            "--iters", str(iters), "--tv-weight", str(tv_weight)]


def run_rsi_round(*, client, held_out_scene_ids, candidates=DEFAULT_GRID,
                  seed_solver_ws, domain: str = "cassi", capability_profile: str = "A1",
                  interaction_mode: str = "I2") -> dict:
    """Score a deterministic grid of GAP-TV solver candidates against every held-out
    scene, letting the control plane compute PSNR, and rank candidates by mean PSNR.

    Runs the whole round under a single control-plane run: the solver code is staged
    once, and each candidate is scored on the full held-out scene set (required by
    /evaluate_candidates), tagging each score_heldout call with the candidate's
    config_id so the control plane can attribute scores per version.
    """
    seed_solver_ws = Path(seed_solver_ws)
    seed_cassi_workspace(seed_solver_ws, seed=42)

    run = client.open_run("rsi round: cassi candidate grid", capability_profile,
                          {"actions": len(candidates) * len(held_out_scene_ids) + 1},
                          interaction_profile=interaction_mode)
    run_id = run["run_id"]

    # Stage the solver code once for the whole round.
    for p in sorted(seed_solver_ws.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(seed_solver_ws).as_posix()
        if rel in _NEVER_STAGE:
            continue
        client.stage_input(run_id, rel, p.read_bytes())

    results = []
    for cfg in candidates:
        cid = config_id(cfg)
        scores = []
        for scene_id in held_out_scene_ids:
            client.stage_heldout(run_id, scene_id, domain=domain)
            client.sandbox_execute(run_id, _solver_command(cfg["iters"], cfg["tv_weight"]))
            score = client.score_heldout(run_id, scene_id, version=cid, domain=domain)
            psnr = score.get("psnr") if score else None
            if psnr is not None:
                scores.append(psnr)
        mean_psnr = (sum(scores) / len(scores)) if scores else None
        client.register_version("agent", "imaging", cid,
                                {"iters": cfg["iters"], "tv_weight": cfg["tv_weight"],
                                 "mean_psnr": mean_psnr})
        results.append({"version": cid, "mean_psnr": mean_psnr})

    evaluation = client.evaluate_candidates(run_id, results=results, domain=domain)

    ranked = sorted(
        ((r["version"], r["mean_psnr"]) for r in results),
        key=lambda item: (item[1] is None, -(item[1] or 0.0)),
    )
    return {"ranked": ranked, "eval_ref": evaluation.get("eval_ref")}
