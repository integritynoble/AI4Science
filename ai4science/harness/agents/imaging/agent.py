from __future__ import annotations
from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.verifier import PhysicsJudgeVerifier, ExternalEvaluatorVerifier
from ai4science.harness.runtime.pev import run_task
from .benchmark import seed_cassi_workspace
from .planner import ReferenceImagingPlanner

# Security: answer key must never reach the untrusted sandbox where a compromised solver
# could copy it to results/reconstruction_xhat.npy and pass the reference-free judge.
_NEVER_STAGE = {"data/ground_truth_x.npy"}

def run_imaging_task(*, workspace, client, store, task_id, interaction_mode: str = "I2",
                     capability_profile: str = "A1", seed: int = 42, max_repairs: int = 2,
                     on_ask=None, planner=None, governed: bool = True, agent_id: str | None = None) -> dict:
    """Seed a CASSI benchmark locally, stage it into the run's sandbox workspace, then drive
    the dual-mode runtime to a physics-verified reconstruction (judged in the run workspace).
    When agent_id is set, the run binds to that foundry agent and its CP-derived ceiling
    (not the caller-passed capability_profile) governs the run + contract."""
    workspace = Path(workspace)
    seed_cassi_workspace(workspace, seed=seed)
    from ai4science.harness.agents.specs.imaging import AGENT
    run = client.open_run("cassi reconstruction", capability_profile,
                          {"actions": max_repairs + 3}, interaction_profile=interaction_mode,
                          agent_id=agent_id)
    contract_profile = run.get("capability_profile", capability_profile) if agent_id else capability_profile
    contract = compile_contract(
        objective="reconstruct the CASSI scene",
        capability_profile=contract_profile,
        interaction_mode=interaction_mode,
        deliverables=["results/reconstruction_xhat.npy"],
        success_criteria=["judge final_decision == pass"],
        approval_required_for=list(AGENT.approval_required_for),
    )
    run_ws = Path(run["workspace_path"])
    # Stage the seeded inputs into the run's confined sandbox workspace.
    for p in sorted(workspace.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(workspace).as_posix()
        if rel in _NEVER_STAGE:
            continue
        client.stage_input(run["run_id"], rel, p.read_bytes())
    if planner is not None:
        run_planner = planner
    else:
        meta = None
        if governed:
            try:
                lkg = client.get_last_known_good("agent", "imaging")
            except Exception:
                lkg = None
            meta = (lkg or {}).get("metadata") if lkg else None
        if meta and "iters" in meta and "tv_weight" in meta:
            run_planner = ReferenceImagingPlanner(base_iters=int(meta["iters"]),
                                                  tv_weight=float(meta["tv_weight"]),
                                                  max_repairs=max_repairs)
        else:
            run_planner = ReferenceImagingPlanner(max_repairs=max_repairs)
    verifier = (ExternalEvaluatorVerifier(client, run["run_id"]) if governed
                else PhysicsJudgeVerifier(run_ws))
    result = run_task(run_id=run["run_id"], contract=contract, client=client,
                      planner=run_planner,
                      verifier=verifier, store=store, task_id=task_id,
                      on_ask=on_ask)
    result["judge_report"] = str(run_ws / "reports" / "judge_report.json")
    return result
