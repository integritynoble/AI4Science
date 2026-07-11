from pathlib import Path
import numpy as np
from ai4science.harness.agents.imaging.benchmark import seed_cassi_workspace
from ai4science.judge.cassi.judge_cassi import judge_cassi

def test_seed_populates_workspace(tmp_path):
    meta = seed_cassi_workspace(tmp_path, seed=42)
    for rel in ["spec.md", "benchmark.md",
                "code/run_solver.py", "code/cassi.py", "code/gap_tv.py",
                "data/measurement_y.npy", "data/coded_aperture_phi.npy", "data/ground_truth_x.npy"]:
        assert (tmp_path / rel).exists(), f"seed missing {rel}"
    y = np.load(tmp_path / "data" / "measurement_y.npy")
    mask = np.load(tmp_path / "data" / "coded_aperture_phi.npy")
    # sheared model: y width = mask width + C - 1  (so y is WIDER than the mask)
    assert y.shape[0] == mask.shape[0] and y.shape[1] > mask.shape[1]
    assert meta["seed"] == 42

def test_seeded_benchmark_is_solvable_ground_truth_passes_judge(tmp_path):
    # Sanity: the ground truth reconstructs the measurement, so the judge's S1/S3 pass
    # and S4 forward-residual passes when we submit the ground truth as the reconstruction.
    seed_cassi_workspace(tmp_path, seed=42)
    (tmp_path / "results").mkdir(exist_ok=True)
    gt = np.load(tmp_path / "data" / "ground_truth_x.npy")
    np.save(tmp_path / "results" / "reconstruction_xhat.npy", gt)
    report = judge_cassi(tmp_path)
    assert report["s1_status"] == "pass"
    assert report["s3_status"] == "pass"
    assert report["s4_checks"]["forward_residual"]["status"] == "pass"
    assert report["final_decision"] in ("pass", "needs_review")
    assert report["silent_failure"] is False
