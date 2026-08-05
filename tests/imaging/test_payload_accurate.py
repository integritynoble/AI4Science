from pathlib import Path
import numpy as np
from ai4science.harness.agents.imaging.benchmark import seed_cassi_workspace
from ai4science.harness.agents.imaging import PAYLOAD_DIR
from ai4science.judge.cassi.judge_cassi import judge_cassi

def test_spec_describes_the_real_fixture():
    spec = (PAYLOAD_DIR / "spec.md").read_text()
    # The SHIPPED template must describe the real fixture, not just the copy
    # that generate_data.py rewrites per instance. Left alone, the template
    # would keep claiming 32x32x8 for a 64x64x8 benchmark and this test would
    # pass while the sentence it checks was false.
    assert "(64, 64, 8)" in spec and "(64, 71)" in spec
    assert "32x32x8" not in spec    # the stale synthetic-fixture numbers are gone
    assert "256" not in spec        # and the stale 256x256x28 ones before them

def test_regenerated_docs_still_judge_valid(tmp_path):
    seed_cassi_workspace(tmp_path, seed=42)
    (tmp_path / "results").mkdir(exist_ok=True)
    gt = np.load(tmp_path / "data" / "ground_truth_x.npy")
    np.save(tmp_path / "results" / "reconstruction_xhat.npy", gt)
    report = judge_cassi(tmp_path)
    assert report["s1_status"] == "pass" and report["s3_status"] == "pass"
