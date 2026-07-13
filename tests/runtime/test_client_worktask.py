from ai4science.harness.control_plane.client import ControlPlaneClient

def test_stage_worktask_fail_closed_on_dead_socket(tmp_path):
    c = ControlPlaneClient(str(tmp_path / "no.sock"), timeout=0.2)
    assert c.stage_worktask("r1", 0)["ok"] is False

def test_score_worktask_fail_closed_on_dead_socket(tmp_path):
    c = ControlPlaneClient(str(tmp_path / "no.sock"), timeout=0.2)
    r = c.score_worktask("r1", 0, version="v")
    assert r["pass"] == 0.0 and r["steps"] == 0
