import json
from pathlib import Path

from ai4science.harness.agents.machine.claude_driver import (
    drive_claude, ensure_governance_hook,
)


def test_ensure_governance_hook_writes_pretooluse(tmp_path):
    p = ensure_governance_hook(tmp_path, ceiling="A1")
    assert p == tmp_path / ".claude" / "settings.json"
    cfg = json.loads(p.read_text())
    hook = cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "PWM_CEILING=A1" in hook and "ai4science.harness.agents.machine.hook" in hook
    # self-sufficient: embeds a PYTHONPATH that can import ai4science
    assert "PYTHONPATH=" in hook
    import ai4science, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(ai4science.__file__)))
    assert root in hook


def test_drive_claude_wires_hook_and_runs(tmp_path):
    seen = {}
    def fake_run(claude_bin, task, project_dir, timeout):
        seen.update(bin=claude_bin, task=task, project_dir=project_dir)
        return {"ok": True, "output": "done"}
    out = drive_claude("write fib.py", project_dir=tmp_path, run=fake_run)
    assert out["ok"] is True and out["governed"] is True and out["ceiling"] == "A1"
    assert seen["task"] == "write fib.py"
    assert (tmp_path / ".claude" / "settings.json").exists()      # hook wired


def test_drive_claude_empty_task_refused(tmp_path):
    out = drive_claude("   ", project_dir=tmp_path, run=lambda *a: {"ok": True})
    assert out["ok"] is False and "empty" in out["reason"]


def test_drive_claude_reports_claude_missing(tmp_path):
    def missing(*a):
        raise FileNotFoundError()
    # _default_run handles FileNotFoundError; simulate via the real default by a bad bin
    out = drive_claude("task", project_dir=tmp_path, claude_bin="definitely-not-a-real-binary-xyz")
    assert out["ok"] is False and "not installed" in out["reason"]


def test_drive_claude_can_skip_hook(tmp_path):
    out = drive_claude("task", project_dir=tmp_path, ensure_hook=False,
                       run=lambda *a: {"ok": True})
    assert out["ok"] is True
    assert not (tmp_path / ".claude").exists()      # hook not wired when disabled


def test_approval_mode_reflects_telegram_config(monkeypatch):
    from ai4science.harness.agents.machine.claude_driver import approval_mode
    monkeypatch.delenv("PWM_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("PWM_TELEGRAM_CHAT_ID", raising=False)
    assert approval_mode() == "local"
    monkeypatch.setenv("PWM_TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("PWM_TELEGRAM_CHAT_ID", "1")
    assert approval_mode() == "telegram"


def test_guide_needs_goal_when_empty():
    from ai4science.harness.agents.machine.claude_driver import guide_session
    r = guide_session(project_dir="/x", goal="")
    assert r["needs_goal"] is True and "goal" in r["question"].lower()


def test_guide_loops_until_goal_met(tmp_path):
    from ai4science.harness.agents.machine.claude_driver import guide_session
    calls = []
    outputs = ["working on it... GOAL_NOT_MET: still need to tune",
               "tuned and verified. GOAL_MET"]
    def fake_drive(task, **kw):
        calls.append(task)
        return {"ok": True, "output": outputs[len(calls) - 1]}
    r = guide_session(project_dir=str(tmp_path), goal="make PSNR > 25", ceiling="A2",
                      max_rounds=5, seed_from_transcript=False, drive=fake_drive)
    assert r["met"] is True and r["rounds"] == 2
    assert "make PSNR > 25" in calls[0]                       # goal injected
    assert "Continue from exactly there" in calls[1]         # round 2 fed the prior output


def test_guide_stops_at_round_limit_unmet(tmp_path):
    from ai4science.harness.agents.machine.claude_driver import guide_session
    r = guide_session(project_dir=str(tmp_path), goal="impossible", max_rounds=2,
                      seed_from_transcript=False,
                      drive=lambda task, **kw: {"ok": True, "output": "GOAL_NOT_MET: nope"})
    assert r["met"] is False and r["rounds"] == 2 and "round limit" in r["note"]


def test_guide_aborts_on_drive_failure(tmp_path):
    from ai4science.harness.agents.machine.claude_driver import guide_session
    r = guide_session(project_dir=str(tmp_path), goal="x", seed_from_transcript=False,
                      drive=lambda task, **kw: {"ok": False, "reason": "claude timed out"})
    assert r["ok"] is False and r["reason"] == "claude timed out" and r["rounds"] == 1
