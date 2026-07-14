from pathlib import Path

from ai4science.harness.agents.manager.input_staging import (
    prepare_run_kwargs, stage_workspace, input_spec,
)


def test_advisory_agent_maps_to_demand_kwargs():
    out = prepare_run_kwargs("manager", "route this")
    assert out["ok"] is True and out["kwargs"] == {"demand": {"intent": "route this"}}


def test_unknown_agent_defaults_to_advisory():
    out = prepare_run_kwargs("mystery", "hello")
    assert out["ok"] is True and out["kwargs"] == {"demand": {"intent": "hello"}}


def test_input_agent_fail_closed_without_workspace():
    out = prepare_run_kwargs("imaging", "reconstruct the cassi scene")
    assert out["ok"] is False and out["missing"] == ["workspace"]
    assert "needs input" in out["reason"]


def test_input_agent_with_workspace_maps_to_workspace_kwarg():
    out = prepare_run_kwargs("imaging", "reconstruct", {"workspace": "/data/scene"})
    assert out["ok"] is True and out["kwargs"] == {"workspace": "/data/scene"}


def test_input_spec_declares_required():
    assert input_spec("work").required == ("workspace",)
    assert input_spec("manager").required == ()


# --- stage_workspace (confined staging via a fake stage) ---------------------

def test_stage_workspace_walks_dir_and_stages_each_file(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"AAA")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "b.bin").write_bytes(b"BBB")
    staged = []
    def fake_stage(run_id, rel, content):
        staged.append((run_id, rel, content))
    out = stage_workspace(str(tmp_path), run_id="r1", stage=fake_stage)
    assert out["ok"] is True and sorted(out["staged"]) == ["a.txt", "sub/b.bin"]
    by_rel = {rel: content for _, rel, content in staged}
    assert by_rel["a.txt"] == b"AAA" and by_rel["sub/b.bin"] == b"BBB"


def test_stage_workspace_fail_closed_on_stage_error(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x")
    def boom(run_id, rel, content):
        raise RuntimeError("cp down")
    out = stage_workspace(str(tmp_path), run_id="r1", stage=boom)
    assert out["ok"] is False and "failed" in out["reason"]


def test_stage_workspace_needs_a_stage_or_client():
    assert stage_workspace("/tmp", client=None, run_id="r1")["ok"] is False


def test_stage_workspace_rejects_non_directory(tmp_path):
    f = tmp_path / "not_a_dir"; f.write_text("x")
    assert stage_workspace(str(f), run_id="r1", stage=lambda *a: None)["ok"] is False


def test_workspace_passthrough_run_params():
    out = prepare_run_kwargs("imaging", "recon", {"workspace": "/d", "seed": 7, "governed": False})
    assert out["kwargs"] == {"workspace": "/d", "seed": 7, "governed": False}
