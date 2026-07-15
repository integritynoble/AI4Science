import json

from ai4science.harness.agents.machine.sessions import find_claude_sessions, _looks_like_claude
from ai4science.harness.agents.machine.agent import run_machine


def test_looks_like_claude():
    assert _looks_like_claude(["/home/u/.local/bin/claude", "-p", "task"])
    assert _looks_like_claude(["node", "/opt/claude", "chat"])
    assert not _looks_like_claude(["python3", "-m", "pytest"])


def test_find_sessions_reports_governance(tmp_path):
    # a project with the governance hook wired
    gov = tmp_path / "gov"
    (gov / ".claude").mkdir(parents=True)
    (gov / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "*", "hooks": [{"type": "command",
         "command": "PWM_CEILING=A1 python3 -m ai4science.harness.agents.machine.hook"}]}]}}))
    ungov = tmp_path / "plain"; ungov.mkdir()

    def fake_procs():
        return [{"pid": 111, "args": ["claude", "-p", "do x"], "cwd": str(gov)},
                {"pid": 222, "args": ["/x/claude", "chat"], "cwd": str(ungov)}]

    out = find_claude_sessions(list_procs=fake_procs)
    assert out["count"] == 2 and out["manageable_count"] == 2
    by_pid = {s["pid"]: s for s in out["manageable"]}
    assert by_pid[111]["governed"] is True and by_pid[111]["ceiling"] == "A1"
    assert by_pid[222]["governed"] is False
    assert "pid 111" in out["summary"] and "governed" in out["summary"]


def test_find_sessions_splits_mine_vs_others():
    def procs():
        return [{"pid": 1, "args": ["claude"], "cwd": "/home/me/proj"},   # mine
                {"pid": 2, "args": ["claude"], "cwd": None}]              # other user
    out = find_claude_sessions(list_procs=procs)
    assert out["manageable_count"] == 1 and out["others_count"] == 1
    assert "other users" in out["summary"]


def test_find_sessions_empty_when_none():
    out = find_claude_sessions(list_procs=lambda: [])
    assert out["count"] == 0 and out["manageable"] == []
    assert "No running Claude Code sessions" in out["summary"]


def test_machine_agent_routes_find_sessions():
    caps = {"os": "linux", "installed": {}, "supported": True}
    out = run_machine(intent="find running claude sessions", caps=caps)
    assert out["status"] == "done" and out["op"] == "find_sessions"
    assert "manageable" in out["result"] and "summary" in out["result"]
