import pytest
from ai4science.harness.agents.machine import pause


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PWM_TRUST_OWNER", "tester")


def test_pause_resume_roundtrip():
    assert pause.is_paused() is False
    assert pause.pause() is True
    assert pause.is_paused() is True
    assert pause.resume() is True
    assert pause.is_paused() is False
    assert pause.resume() is True                 # idempotent


def test_guide_waits_while_paused_then_runs(tmp_path):
    from ai4science.harness.agents.machine.claude_driver import guide_session
    # paused for the first 2 checks, then resumed
    state = {"n": 0}
    def paused():
        state["n"] += 1
        return state["n"] <= 2
    events = []
    r = guide_session(project_dir=str(tmp_path), goal="x", verify=False,
                      seed_from_transcript=False, max_rounds=1,
                      is_paused=paused, sleep=lambda s: None, notify=events.append,
                      drive=lambda task, **kw: {"ok": True, "output": "GOAL_MET"})
    assert r["met"] is True and r["rounds"] == 1
    assert any("paused" in e for e in events) and any("resumed" in e for e in events)


def test_hook_denies_while_paused(tmp_path, monkeypatch):
    import json, subprocess, sys, os
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PWM_TRUST_OWNER", "tester")
    pause.pause()                                  # machine paused
    payload = json.dumps({"session_id": "s", "tool_name": "Read", "tool_input": {"file_path": "/x"}})
    p = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                       input=payload, capture_output=True, text=True, env={**os.environ})
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "paused" in out["permissionDecisionReason"]
