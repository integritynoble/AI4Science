from ai4science.harness.agents.imaging.planner import ReferenceImagingPlanner


def test_planner_threads_tv_weight():
    p = ReferenceImagingPlanner(base_iters=160, tv_weight=0.05)
    step = p.next_step(state=None)
    assert "--tv-weight" in step.command
    i = step.command.index("--tv-weight")
    assert step.command[i + 1] == "0.05"
    assert "160" in step.command


def test_run_imaging_task_uses_promoted_config(tmp_path, monkeypatch):
    # stub client whose get_last_known_good returns {"metadata": {"iters":240,"tv_weight":0.02}}
    # and capture the FIRST sandbox_execute command to assert it used iters=240, tv=0.02.
    captured = {}

    class Stub:
        def open_run(self, *a, **k):
            return {"run_id": "R", "workspace_path": str(tmp_path / "ws"),
                     "capability_profile": "A1", "limits": {}}

        def stage_input(self, *a, **k):
            return {"ok": True}

        def classify(self, *a, **k):
            return {"decision": "ACT"}

        def get_last_known_good(self, kind, name):
            return {"version": "v", "metadata": {"iters": 240, "tv_weight": 0.02}}

        def sandbox_execute(self, run_id, command, **k):
            captured.setdefault("cmd", command)
            return {"is_error": False, "exit_code": 0, "artifacts": []}

        def evaluate(self, run_id):
            return {"decision": "pass", "score": 0.0, "feedback": {}}

    from ai4science.harness.agents.imaging.agent import run_imaging_task
    from ai4science.harness.runtime.task_store import TaskStore

    run_imaging_task(workspace=tmp_path / "seed", client=Stub(), store=TaskStore(tmp_path / "t"),
                      task_id="lc", interaction_mode="I2", governed=True)
    assert "240" in captured["cmd"] and "0.02" in captured["cmd"]
