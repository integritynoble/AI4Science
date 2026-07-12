from pathlib import Path
import numpy as np
from ai4science.harness.agents.imaging.benchmark import seed_cassi_workspace
from ai4science.harness.agents.imaging import PAYLOAD_DIR
from ai4science.judge.cassi.judge_cassi import judge_cassi

def test_spec_describes_the_real_fixture():
    spec = (PAYLOAD_DIR / "spec.md").read_text()
    assert "(32, 32, 8)" in spec and "(32, 39)" in spec
    assert "256" not in spec        # the stale 256x256x28 numbers are gone

def test_regenerated_docs_still_judge_valid(tmp_path):
    seed_cassi_workspace(tmp_path, seed=42)
    (tmp_path / "results").mkdir(exist_ok=True)
    gt = np.load(tmp_path / "data" / "ground_truth_x.npy")
    np.save(tmp_path / "results" / "reconstruction_xhat.npy", gt)
    report = judge_cassi(tmp_path)
    assert report["s1_status"] == "pass" and report["s3_status"] == "pass"
