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


def test_govern_session_wires_hook_and_adopts():
    calls = {}
    def wire(cwd, *, ceiling):
        calls["cwd"], calls["ceiling"] = cwd, ceiling
        return f"{cwd}/.claude/settings.json"
    def adopt(*, pid, cwd, name, ceiling):
        calls["adopt"] = (pid, cwd, name, ceiling)
        return {"name": "proj"}
    r = govern_session(999, ceiling="A2", name="proj",
                       cwd_of=lambda pid: "/home/me/proj", wire=wire, adopt=adopt)
    assert r["ok"] and r["project_dir"] == "/home/me/proj" and r["ceiling"] == "A2"
    assert r["name"] == "proj" and "RESTARTED" in r["note"]
    assert calls["adopt"] == (999, "/home/me/proj", "proj", "A2")


def test_govern_session_creates_real_record(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.machine import supervisor as sup
    r = govern_session(4242, ceiling="A1", cwd_of=lambda pid: "/home/me/scratch",
                       wire=lambda *a, **k: "settings.json")
    assert r["ok"] and r["name"] == "scratch"
    assert sup.get_by_pid(4242)["ceiling"] == "A1"


def test_govern_session_fails_when_cwd_unreadable():
    r = govern_session(999, cwd_of=lambda pid: None, wire=lambda *a, **k: "x")
    assert r["ok"] is False and "can't read" in r["reason"]


def test_find_sessions_join_shows_supervisor_name(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.machine import supervisor as sup
    sup.create(pid=777, cwd="/home/me/proj", name="exporter", ceiling="A2", alive=lambda p: True)

    out = find_claude_sessions(list_procs=lambda: [
        {"pid": 777, "args": ["claude"], "cwd": "/home/me/proj"},
        {"pid": 888, "args": ["claude"], "cwd": "/home/me/plain"}])
    by_pid = {s["pid"]: s for s in out["manageable"]}
    assert by_pid[777]["name"] == "exporter" and by_pid[777]["supervised"] is True
    assert by_pid[777]["ceiling"] == "A2" and by_pid[777]["governed"] is True
    assert by_pid[888]["name"] is None and by_pid[888]["supervised"] is False
    assert "exporter" in out["summary"] and "pid 777" in out["summary"]


def test_find_sessions_includes_intro(tmp_path):
    repo = tmp_path / "myproj"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/feature-x\n")

    def procs():
        return [{"pid": 4242, "args": ["claude", "-p", "build the exporter"], "cwd": str(repo)},
                {"pid": 4243, "args": ["claude"], "cwd": str(tmp_path / "plain")}]
    (tmp_path / "plain").mkdir()

    out = find_claude_sessions(list_procs=procs)
    by_pid = {s["pid"]: s for s in out["manageable"]}
    assert "myproj repo @ feature-x" in by_pid[4242]["intro"]
    assert "task:" in by_pid[4242]["intro"] and "build the exporter" in by_pid[4242]["intro"]
    assert "interactive" in by_pid[4243]["intro"]
    assert "myproj repo @ feature-x" in out["summary"]      # the intro reaches the rendered list


def test_intro_reads_transcript_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from ai4science.harness.agents.machine.sessions import describe_session
    cwd = "/work/myproj"
    proj = tmp_path / ".claude" / "projects" / cwd.replace("/", "-")
    proj.mkdir(parents=True)
    (proj / "sess.jsonl").write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "old request"}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": "working..."}}) + "\n" +
        json.dumps({"type": "user", "message": {"role": "user",
                    "content": [{"type": "text", "text": "tune the GAP-TV weights"}]}}) + "\n")
    intro = describe_session(cwd, ["claude"], None)      # interactive → peeks the transcript
    assert "interactive" in intro and 'doing: "tune the GAP-TV weights"' in intro


def test_intro_activity_absent_when_no_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))            # empty home, no transcripts
    from ai4science.harness.agents.machine.sessions import describe_session
    intro = describe_session("/work/other", ["claude"], None)
    assert "interactive" in intro and "doing:" not in intro


def test_machine_agent_routes_find_sessions():
    caps = {"os": "linux", "installed": {}, "supported": True}
    out = run_machine(intent="find running claude sessions", caps=caps)
    assert out["status"] == "done" and out["op"] == "find_sessions"
    assert "manageable" in out["result"] and "summary" in out["result"]
