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
