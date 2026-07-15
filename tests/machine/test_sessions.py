import json

from ai4science.harness.agents.machine.sessions import (
    find_claude_sessions, _looks_like_claude, stop_session, govern_session)
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


def test_stop_session_sends_signal_to_owned_pid():
    sent = {}
    def fake_kill(pid, sig):
        sent["pid"], sent["sig"] = pid, sig
    r = stop_session("250238", kill=fake_kill)
    assert r["ok"] and r["pid"] == 250238 and sent["pid"] == 250238


def test_stop_session_reports_gone_and_foreign_and_bad_pid():
    def gone(pid, sig): raise ProcessLookupError
    def foreign(pid, sig): raise PermissionError
    assert stop_session(1, kill=gone)["ok"] is False
    r = stop_session(1, kill=foreign)
    assert r["ok"] is False and "not owned by you" in r["reason"]
    assert stop_session("notapid", kill=lambda *a: None)["ok"] is False


def test_govern_session_wires_hook_in_session_cwd():
    calls = {}
    def wire(cwd, *, ceiling):
        calls["cwd"], calls["ceiling"] = cwd, ceiling
        return f"{cwd}/.claude/settings.json"
    r = govern_session(999, ceiling="A2", cwd_of=lambda pid: "/home/me/proj", wire=wire)
    assert r["ok"] and r["project_dir"] == "/home/me/proj" and r["ceiling"] == "A2"
    assert calls["cwd"] == "/home/me/proj" and calls["ceiling"] == "A2"
    assert "RESTARTED" in r["note"]


def test_govern_session_fails_when_cwd_unreadable():
    r = govern_session(999, cwd_of=lambda pid: None, wire=lambda *a, **k: "x")
    assert r["ok"] is False and "can't read" in r["reason"]


def test_machine_agent_routes_find_sessions():
    caps = {"os": "linux", "installed": {}, "supported": True}
    out = run_machine(intent="find running claude sessions", caps=caps)
    assert out["status"] == "done" and out["op"] == "find_sessions"
    assert "manageable" in out["result"] and "summary" in out["result"]
