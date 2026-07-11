from __future__ import annotations
from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.verifier import PhysicsJudgeVerifier
from ai4science.harness.runtime.pev import run_task
from .benchmark import seed_cassi_workspace
from .planner import ReferenceImagingPlanner

def run_imaging_task(*, workspace, client, store, task_id, interaction_mode: str = "I2",
                     capability_profile: str = "A1", seed: int = 42, max_repairs: int = 2,
                     on_ask=None) -> dict:
    """Seed a CASSI benchmark, then drive the dual-mode runtime to a physics-verified
    reconstruction (I2 autonomous / I0-I1 propose-then-approve)."""
    workspace = Path(workspace)
    seed_cassi_workspace(workspace, seed=seed)
    # Pull the agent's declared approval envelope from its manifest.
    from ai4science.harness.agents.specs.imaging import AGENT
    contract = compile_contract(
        objective="reconstruct the CASSI scene",
        capability_profile=capability_profile,
        interaction_mode=interaction_mode,
        deliverables=["results/reconstruction_xhat.npy"],
        success_criteria=["judge final_decision == pass"],
        approval_required_for=list(AGENT.approval_required_for),
    )
    run = client.open_run("cassi reconstruction", capability_profile,
                          {"actions": max_repairs + 3}, interaction_profile=interaction_mode)
    result = run_task(run_id=run["run_id"], contract=contract, client=client,
                      planner=ReferenceImagingPlanner(max_repairs=max_repairs),
                      verifier=PhysicsJudgeVerifier(workspace), store=store, task_id=task_id,
                      on_ask=on_ask)
    result["judge_report"] = str(workspace / "reports" / "judge_report.json")
    return result
