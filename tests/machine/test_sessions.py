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


def test_continuation_task_seeds_from_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from ai4science.harness.agents.machine.sessions import continuation_task
    cwd = "/work/cassi"
    proj = tmp_path / ".claude" / "projects" / cwd.replace("/", "-")
    proj.mkdir(parents=True)
    (proj / "s.jsonl").write_text(
        json.dumps({"type": "user", "message": {"content": "implement gap-tv"}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": "tv_weight 12.0 was 100x too strong; optimum ~0.05"}}) + "\n" +
        json.dumps({"type": "user", "message": {"content": "please continue the gap-tv tuning"}}) + "\n")
    task = continuation_task(cwd)
    assert "please continue the gap-tv tuning" in task
    assert "tv_weight 12.0" in task and "Resume" in task


def test_continuation_task_none_without_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from ai4science.harness.agents.machine.sessions import continuation_task
    assert continuation_task("/work/empty") is None


def test_session_state_working_vs_idle(tmp_path, monkeypatch):
    import os, time
    monkeypatch.setenv("HOME", str(tmp_path))
    from ai4science.harness.agents.machine.sessions import _session_state, describe_session
    cwd = "/work/live"
    proj = tmp_path / ".claude" / "projects" / cwd.replace("/", "-")
    proj.mkdir(parents=True)
    tr = proj / "s.jsonl"
    tr.write_text(json.dumps({"type": "user", "message": {"content": "go"}}) + "\n")
    # just-written transcript → working
    assert _session_state(cwd)[0] == "working"
    assert "WORKING" in describe_session(cwd, ["claude"], None)
    # backdate the transcript → idle
    old = time.time() - 3600
    os.utime(tr, (old, old))
    assert _session_state(cwd)[0] == "idle"
    assert "idle" in describe_session(cwd, ["claude"], None)


def test_machine_agent_routes_find_sessions():
    caps = {"os": "linux", "installed": {}, "supported": True}
    out = run_machine(intent="find running claude sessions", caps=caps)
    assert out["status"] == "done" and out["op"] == "find_sessions"
    assert "manageable" in out["result"] and "summary" in out["result"]


def test_send_to_session_sends_text_and_enter():
    from ai4science.harness.agents.machine.sessions import send_to_session
    sent = []
    r = send_to_session("work", text="1", enter=True,
                        resolve=lambda s: 4242, target="work:0.0",
                        run=lambda a: (sent.append(a) or (0, "")))
    assert r["ok"] and r["target"] == "work:0.0"
    assert sent[0] == ["tmux", "send-keys", "-t", "work:0.0", "-l", "--", "1"]   # literal text
    assert sent[1] == ["tmux", "send-keys", "-t", "work:0.0", "Enter"]           # then Enter


def test_send_to_session_refuses_non_tmux():
    from ai4science.harness.agents.machine.sessions import send_to_session
    r = send_to_session("work", text="hi", resolve=lambda s: 4242, target=None,
                        run=lambda a: (0, ""))
    assert r["ok"] is False and "not in tmux" in r["reason"]


def test_send_to_session_unknown_name():
    from ai4science.harness.agents.machine.sessions import send_to_session
    r = send_to_session("nope", text="x", resolve=lambda s: None, run=lambda a: (0, ""))
    assert r["ok"] is False and "no session" in r["reason"]


def test_tmux_target_for_pid_matches_ancestor_pane(monkeypatch):
    from ai4science.harness.agents.machine import sessions as S
    monkeypatch.setattr(S, "_proc_ancestors", lambda pid: {pid, 5000, 6000})
    panes = "6000 work:0.0\n7777 other:1.0\n"
    assert S.tmux_target_for_pid(4242, run=lambda a: (panes, 0)) == "work:0.0"
    assert S.tmux_target_for_pid(4242, run=lambda a: ("9999 x:0.0\n", 0)) is None


def test_operate_answers_prompts_then_exits_on_idle():
    from ai4science.harness.agents.machine.sessions import operate_session
    panes = ["❯ 1. Yes\n  3. No\nDo you want to X?",   # prompt → answer
             "❯ 1. Yes\n  3. No",                       # prompt → answer
             "idle >", "idle >", "idle >", "idle >"]    # quiet → idle-exit
    it = iter(panes)
    sent = []
    r = operate_session("work", target="work:0.0", resolve=lambda s: 4242,
                        clients=lambda s: [],                       # nobody attached
                        capture=lambda t: next(it, "idle >"),
                        send=lambda t, k, en: sent.append((t, k, en)),
                        sleep=lambda s: None, log=lambda m: None,
                        poll=1.0, idle_exit=3.0, max_answers=10)
    assert r["ok"] and r["answers"] == 2 and r["stopped"] == "idle"
    assert sent[0] == ("work:0.0", "1", False)           # answered with the default choice


def test_operate_yields_while_you_are_attached():
    from ai4science.harness.agents.machine.sessions import operate_session
    sent = []
    r = operate_session("work", target="work:0.0", resolve=lambda s: 1,
                        clients=lambda s: ["client x"],             # a human is attached the whole time
                        capture=lambda t: "❯ 1. Yes\n3. No",        # a prompt is showing…
                        send=lambda t, k, en: sent.append(k),
                        sleep=lambda s: None, log=lambda m: None,
                        poll=1.0, idle_exit=100, max_answers=10, max_iters=5)
    assert r["stopped"] == "iter-cap" and r["answers"] == 0 and sent == []   # …but it never sent while you're attached


def test_pane_wants_answer_detection():
    from ai4science.harness.agents.machine.sessions import _pane_wants_answer
    assert _pane_wants_answer("Do you want to create tune.py?\n❯ 1. Yes\n  3. No")
    assert not _pane_wants_answer("● Running the sweep…")
    assert not _pane_wants_answer("$ ")


def test_start_session_creates_tmux_and_record():
    from ai4science.harness.agents.machine.sessions import start_session
    calls = []
    def fake_run(args):
        calls.append(args)
        if args[:2] == ["tmux", "list-panes"]:
            return (0, "55123\n", "")
        return (0, "", "")                                    # new-session ok
    reg = {}
    r = start_session("work", cwd="/home/me/proj", run=fake_run,
                      register=lambda **kw: reg.update(kw) or {"name": "work"})
    assert r["ok"] and r["name"] == "work" and r["pid"] == 55123 and r["target"] == "work:0.0"
    assert calls[0][:3] == ["tmux", "new-session", "-d"] and "/home/me/proj" in calls[0]
    assert reg["pid"] == 55123 and reg["cwd"] == "/home/me/proj"


def test_start_session_govern_wires_hook_before_start():
    from ai4science.harness.agents.machine.sessions import start_session
    order = []
    start_session("g", cwd="/p", govern=True, ceiling="A2",
                  wire=lambda cwd, *, ceiling: order.append(("wire", cwd, ceiling)),
                  run=lambda a: order.append(("run", a[1])) or (0, "9\n" if a[1] == "list-panes" else "", ""),
                  register=lambda **kw: {"name": "g"})
    assert order[0][0] == "wire"                              # hook wired BEFORE new-session
    assert any(o[0] == "run" and o[1] == "new-session" for o in order)


def test_start_session_reports_tmux_failure():
    from ai4science.harness.agents.machine.sessions import start_session
    r = start_session("x", cwd="/p", run=lambda a: (1, "", "no server running"),
                      register=lambda **kw: {})
    assert r["ok"] is False and "could not start" in r["reason"]
