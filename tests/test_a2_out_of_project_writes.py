"""A2 is trusted to work, not trusted to write anywhere.

Asked directly, the hook answered:

    Write /etc/passwd   ceiling A2  ->  allow
        "sensitive/out-of-project write (A2+)"

A2 is what `release` gives every task, so that is the standing authority of an
ordinary released run. For a `claude-code` session the hook is the **only**
boundary in force: the declared paths bound `blast`'s reporting and the
harness's own tools, and bound nothing about what the session can do. So
`blast` saying *"nothing observed outside the declared paths"* was a true report
about what happened and never a statement about what could.

The fix is a narrowing, and it has a trap in it. Since the session now starts in
the declared working directory, the **task folder is out of project** — so
"out-of-project writes ask" naively applied makes every `plan0.md` edit ask, and
after release nothing answers those. The declared paths have to reach the hook,
which is the principle already written into `assign`:

    Two boundaries that disagree are one boundary and one blind spot.

So: out of project **and not declared** asks, at every ceiling. Inside a
declared root is an in-project write. And genuinely sensitive paths — `/etc`,
`.ssh`, credentials — ask at every ceiling and are not unlocked by declaring
them, because a path that can authorise itself is the hole the declaration
exists to close.
"""
import pytest

from ai4science.harness.agents.machine.session import decide_tool_call


def _write(path, ceiling="A2", project_dir="/work", writable=None):
    return decide_tool_call({"tool_name": "Write",
                             "tool_input": {"file_path": path}},
                            ceiling=ceiling, project_dir=project_dir,
                            writable=writable)


# ── what A2 must stop doing ───────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/etc/passwd",
    "/home/grace/.ssh/id_rsa",
    "/home/grace/somewhere-else/x.md",
    "/usr/local/bin/thing",
])
def test_a2_no_longer_writes_outside_the_project(path):
    assert _write(path)["decision"] == "ask", path


def test_and_says_which_path_it_is_asking_about():
    got = _write("/home/grace/somewhere-else/x.md")
    assert "somewhere-else" in got["reason"]


def test_declaring_a_sensitive_path_does_not_unlock_it():
    """A declaration is the owner naming a working directory, not a key to the
    machine. A path that can authorise itself is the hole this closes."""
    assert _write("/etc/passwd", writable=["/etc"])["decision"] == "ask"
    assert _write("/home/g/.ssh/id_rsa",
                  writable=["/home/g/.ssh"])["decision"] == "ask"


def test_a_protected_path_is_still_denied_outright():
    """Never an ask: the hook's own config and the trust ledger."""
    got = _write("/work/.claude/settings.json")
    assert got["decision"] == "deny"


# ── what must keep working ────────────────────────────────────────────

def test_an_in_project_write_is_unchanged():
    assert _write("/work/out.md")["decision"] == "allow"


def test_a_declared_root_is_treated_as_in_project():
    """The task folder, which the session no longer stands in and still has to
    edit `plan0.md` in. Without this every plan edit asks after release, and
    nothing answers it."""
    got = _write("/home/g/.sarsi/agents/w/tasks/tsk_1/plan0.md",
                 writable=["/home/g/.sarsi/agents/w/tasks/tsk_1"])
    assert got["decision"] == "allow", got


def test_a_declared_root_does_not_leak_to_its_siblings():
    """`/x/work-evil` shares six characters with `/x/work` and is not inside
    it — compared as resolved paths, never as strings."""
    got = _write("/x/work-evil/out.md", writable=["/x/work"])
    assert got["decision"] == "ask"


def test_and_not_to_its_parent():
    got = _write("/x/out.md", writable=["/x/work"])
    assert got["decision"] == "ask"


# ── the lower ceilings are untouched ──────────────────────────────────

def test_a0_still_asks_for_every_write():
    assert _write("/work/out.md", ceiling="A0")["decision"] == "ask"
    assert _write("/work/out.md", ceiling="A0",
                  writable=["/work"])["decision"] == "ask"


def test_a1_still_asks_outside_the_project():
    assert _write("/elsewhere/x.md", ceiling="A1")["decision"] == "ask"


def test_reads_are_untouched():
    got = decide_tool_call({"tool_name": "Read",
                            "tool_input": {"file_path": "/etc/passwd"}},
                           ceiling="A2", project_dir="/work")
    assert got["decision"] == "allow"


# ── and the declared roots have to actually reach the hook ────────────

def test_the_hook_config_carries_the_declared_paths(tmp_path):
    """Otherwise this is the last fix over again: a rule that reads like a
    permission and can never see the thing it depends on."""
    from ai4science.harness.agents.machine.claude_driver import (
        ensure_governance_hook)
    work = tmp_path / "work"
    work.mkdir()
    other = tmp_path / "tsk_1"
    other.mkdir()
    ensure_governance_hook(work, ceiling="A2", writable=[str(other)])
    text = (work / ".claude" / "settings.json").read_text()
    assert "PWM_WRITABLE=" in text
    assert str(other) in text


def test_the_hook_reads_them_back(tmp_path, monkeypatch):
    from ai4science.harness.agents.machine import hook
    monkeypatch.setenv("PWM_WRITABLE", "/a/one:/a/two")
    assert hook._declared_writable() == ["/a/one", "/a/two"]


def test_and_no_declaration_is_an_empty_list(monkeypatch):
    """`None` and `[""]` are different things, and the second would resolve to
    the process's cwd — whatever launched the daemon."""
    from ai4science.harness.agents.machine import hook
    monkeypatch.delenv("PWM_WRITABLE", raising=False)
    assert hook._declared_writable() == []
    monkeypatch.setenv("PWM_WRITABLE", "")
    assert hook._declared_writable() == []


def test_start_session_hands_them_to_the_hook(tmp_path, monkeypatch):
    """The last link. `assign` already computes the declared roots for the
    sandbox; a claude-code session went to `start_session` without them, so the
    hook would have been the one boundary that never heard."""
    from ai4science.harness.agents.machine import sessions
    seen = {}
    monkeypatch.setattr(sessions, "_tmux_run",
                        lambda cmd: (0, "4242", "") if "list-panes" in cmd
                        else (0, "", ""))
    sessions.start_session("s", str(tmp_path), govern=True, ceiling="A2",
                           writable=["/declared/one"],
                           wire=lambda cwd, **kw: seen.update(kw),
                           register=lambda **kw: {"name": "s"})
    assert seen.get("writable") == ["/declared/one"]


def test_and_assign_supplies_them_for_a_claude_code_session(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 session as ses, task as tsk,
                                                 worker as wk)
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    a = c.agents["sarsi-worker"]              # spec: claude-code
    work = tmp_path / "project"
    work.mkdir()
    body = "# g\n\n## Phase 1 — do it\nVerified when: out.md exists\n"
    d = wk.Directive(agent_id=a.id, goal="write the report")
    t = tsk.create(c, a, d)
    (tsk.dir_of(a, t.id) / "plan0.md").write_text(body)
    t = tsk.attach_plan(c, a, t, pl.parse(body))
    t.work_root = str(work)

    seen = {}
    import ai4science.harness.agents.machine.sessions as machine
    monkeypatch.setattr(machine, "start_session",
                        lambda name, cwd, **kw: seen.update(kw) or
                        {"ok": True, "name": name, "pid": 1, "cwd": cwd})
    ses.assign(c, a, t, runtime=ses.MachineRuntime(), installed=lambda: set())
    declared = seen.get("writable") or []
    assert str(tsk.dir_of(a, t.id)) in declared, seen
