"""The sandbox and the blast radius have to be the same boundary.

`do --workdir <dir>` declares where the work happens: evidence is gathered from
there, and `blast` treats it as a path the task is *allowed* to write. The
harness sandbox never heard about it, and mutating tools were confined to the
session's workspace alone. So on a live `jobs` run:

    write /home/grace/live-jobs/positioning.md
      → [blocked] sandbox: path escapes the workspace

    bash "cat > /home/grace/live-jobs/positioning.md <<'EOF' …"
      → written

**The file was written either way.** The sandbox did not prevent the write; it
selected the tool. And it selected the wrong one: `write` names its path, which
is exactly what `blast` reads, while `bash` names nothing — so the one act that
mattered moved from the observed column to the unchecked one, and `blast` could
only report that it could not vouch for it.

That inversion is the bug. A rule that stops the observable route and leaves the
opaque route open does not reduce what an agent can do; it reduces what anyone
can see afterwards. Two boundaries that disagree are one boundary and one hole.

So a declared working directory is writable, and it is writable because it was
**declared in the plan** — the same act that makes it an evidence root and a
blast-radius path. Nothing here widens anything on the agent's say-so:

  * the roots come from the plan, which the owner reads and agrees;
  * the session is launched with them, so widening needs a new session — an
    agent that rewrites its plan mid-run does not thereby gain a directory;
  * everything else stays exactly as sandboxed as it was.

What this does NOT fix, and must not be read as fixing: `bash` is in the
mutating set but takes `cmd`, not `path`, so it was never path-checked and
still is not. `blast` counting shell commands as *unchecked* remains the honest
account of that, and this change makes that count smaller by removing the
reason to reach for a shell, not by inspecting one.
"""
from pathlib import Path

import pytest

from ai4science.harness.agents.sarsi import task as tsk

from ai4science.harness.permissions import PermissionGate


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "task-folder"
    ws.mkdir()
    return ws


@pytest.fixture
def declared(tmp_path):
    d = tmp_path / "live-jobs"
    d.mkdir()
    return d


def _gate(workspace, *, writable=()):
    return PermissionGate(workspace=workspace, read_only=False, auto_yes=True,
                          writable_roots=[Path(w) for w in writable])


# ── the boundary the plan declared ────────────────────────────────────

def test_a_declared_directory_may_be_written(workspace, declared):
    """Observed live: this exact call was refused, and the agent wrote the file
    with a heredoc one step later."""
    gate = _gate(workspace, writable=[declared])
    ok, why = gate.allow("write", {"path": str(declared / "positioning.md"),
                                   "content": "x"})
    assert ok, why


def test_and_edited(workspace, declared):
    gate = _gate(workspace, writable=[declared])
    ok, _ = gate.allow("edit", {"path": str(declared / "positioning.md"),
                                "old": "a", "new": "b"})
    assert ok


def test_a_subdirectory_of_it_too(workspace, declared):
    gate = _gate(workspace, writable=[declared])
    ok, _ = gate.allow("write", {"path": str(declared / "drafts" / "v2.md"),
                                 "content": "x"})
    assert ok


def test_the_workspace_itself_is_still_writable(workspace, declared):
    gate = _gate(workspace, writable=[declared])
    ok, _ = gate.allow("write", {"path": "notes.md", "content": "x"})
    assert ok


# ── and nothing beyond it ─────────────────────────────────────────────

def test_somewhere_else_entirely_is_still_refused(workspace, declared, tmp_path):
    """The point is a boundary that matches the plan, not a wider one."""
    gate = _gate(workspace, writable=[declared])
    ok, why = gate.allow("write", {"path": str(tmp_path / "elsewhere" / "x.md"),
                                   "content": "x"})
    assert not ok and "escapes" in why


def test_a_sibling_that_merely_shares_a_prefix_is_refused(workspace, tmp_path):
    """`/home/grace/live-jobs-evil` is not inside `/home/grace/live-jobs`, and a
    string comparison would say it is."""
    declared = tmp_path / "live-jobs"
    declared.mkdir()
    (tmp_path / "live-jobs-evil").mkdir()
    gate = _gate(workspace, writable=[declared])
    ok, _ = gate.allow("write", {"path": str(tmp_path / "live-jobs-evil" / "x"),
                                 "content": "x"})
    assert not ok


def test_a_traversal_out_of_a_declared_root_is_refused(workspace, declared):
    gate = _gate(workspace, writable=[declared])
    ok, _ = gate.allow("write", {"path": str(declared / ".." / "escaped.md"),
                                 "content": "x"})
    assert not ok


def test_with_nothing_declared_it_is_exactly_as_before(workspace, declared):
    """The default must not move. Most sessions declare no working directory."""
    gate = _gate(workspace)
    ok, why = gate.allow("write", {"path": str(declared / "x.md"),
                                   "content": "x"})
    assert not ok and "escapes" in why


def test_protected_subdirs_are_still_protected(workspace, declared):
    """Widening the root must not smuggle past the judge/hidden_tests rule."""
    gate = _gate(workspace, writable=[declared])
    ok, why = gate.allow("write", {"path": "judge/answers.json", "content": "x"})
    assert not ok and "protected" in why


# ── the two boundaries agree ──────────────────────────────────────────

def test_the_sandbox_allows_exactly_what_blast_calls_declared(tmp_path,
                                                               monkeypatch):
    """The rule this exists to keep. `blast.declared()` is what the report
    treats as permitted; the sandbox is what the session can actually do. When
    they disagree, the difference is not safety — it is a blind spot, because
    the agent reaches for the shell and the act stops being visible."""
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    from ai4science.harness.agents.sarsi import (blast, plan as pl,
                                                 registry as reg, task as tsk,
                                                 worker)
    config = reg.parse(reg.default_config(owner_id="7007143162"),
                       root=tmp_path / "state")
    config.ensure_dirs()
    agent = config.agents["jobs"]
    root = tmp_path / "live-jobs"
    root.mkdir()

    d = worker.Directive(agent_id=agent.id, goal="draft it")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t.work_root = str(root)
    t = tsk._touch(agent, t, __import__("time").time)

    permitted = blast.declared(agent, t)
    gate = _gate(tsk.dir_of(agent, t.id), writable=permitted)
    for path in permitted:
        ok, why = gate.allow("write", {"path": str(Path(path) / "f.md"),
                                       "content": "x"})
        assert ok, f"blast calls {path} declared, the sandbox refuses it: {why}"


# ── and sarsi hands them to the session it starts ─────────────────────

class _Runtime:
    def __init__(self):
        self.started = []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None,
              writable=None):
        self.started.append({"name": name, "cwd": cwd, "spec": spec,
                             "writable": None})
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        return {"ok": True}


    def set_ceiling(self, name, ceiling):
        """Part of the runtime contract — a double omitting it was hidden by a
        swallowed exception in `release` until that stopped being swallowed."""
        return {"name": name, "ceiling": ceiling}

def _sarsi(tmp_path, monkeypatch, *, work_root=None):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 task as tsk, worker)
    config = reg.parse(reg.default_config(owner_id="7007143162"),
                       root=tmp_path / "state")
    config.ensure_dirs()
    agent = config.agents["jobs"]
    d = worker.Directive(agent_id=agent.id, goal="draft it")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    if work_root:
        t.work_root = str(work_root)
    t.plan_agreed = True
    t = tsk._touch(agent, t, __import__("time").time)
    return config, agent, t


def test_the_session_is_launched_able_to_write_where_the_plan_says(
        tmp_path, monkeypatch):
    """The end of the chain. Everything above is inert if the session that
    actually runs is never told."""
    from ai4science.harness.agents.sarsi import session as ses
    root = tmp_path / "live-jobs"
    root.mkdir()
    config, agent, t = _sarsi(tmp_path, monkeypatch, work_root=root)

    seen = {}

    class RT(ses.MachineRuntime):
        def start(self, name, cwd, *, govern, ceiling, env=None,
                  spec="claude-code"):
            seen.update(name=name, cwd=cwd, spec=spec)
            return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    import ai4science.harness.agents.machine.sessions as machine
    calls = {}
    monkeypatch.setattr(machine, "start_session",
                        lambda name, cwd, **kw: calls.update(kw, cwd=cwd) or
                        {"ok": True, "name": name, "pid": 1, "cwd": cwd})
    ses.assign(config, agent, t, runtime=ses.MachineRuntime())
    # The declared root is now the session's CWD, and `PermissionGate` allows
    # `[workspace] + writable_roots` — so being the workspace IS the permission,
    # and a `--writable` for it would be restating it. What the flag now has to
    # carry is the TASK FOLDER, which the session no longer stands in and still
    # has to edit `plan0.md` in.
    launched = calls.get("claude_bin") or ""
    assert str(root) == calls.get("cwd")
    assert f"--writable {tsk.dir_of(agent, t.id)}" in launched


    def set_ceiling(self, name, ceiling):
        """Part of the runtime contract — a double omitting it was hidden by a
        swallowed exception in `release` until that stopped being swallowed."""
        return {"name": name, "ceiling": ceiling}

def test_and_the_task_folder_travels_with_it(tmp_path, monkeypatch):
    """`plan0.md` stays with the task when the session moves. A sandbox
    permitting only the cwd would refuse the one write planning exists for."""
    from ai4science.harness.agents.sarsi import session as ses
    root = tmp_path / "live-jobs"
    root.mkdir()
    config, agent, t = _sarsi(tmp_path, monkeypatch, work_root=root)

    import ai4science.harness.agents.machine.sessions as machine
    calls = {}
    monkeypatch.setattr(machine, "start_session",
                        lambda name, cwd, **kw: calls.update(kw) or
                        {"ok": True, "name": name, "pid": 1, "cwd": cwd})
    ses.assign(config, agent, t, runtime=ses.MachineRuntime())
    assert str(tsk.dir_of(agent, t.id)) in (calls.get("claude_bin") or "")


def test_a_task_with_no_declared_directory_passes_the_desk(tmp_path, monkeypatch):
    """CHANGED by 5-B4. The concern this was written for is unchanged and still
    asserted: never `--writable ''`, which would resolve to whatever launched
    the daemon. What changed is that there is now always something real to
    pass — the worker's desk — so the flag is present and names a directory
    that exists."""
    from ai4science.harness.agents.sarsi import session as ses
    config, agent, t = _sarsi(tmp_path, monkeypatch)

    import ai4science.harness.agents.machine.sessions as machine
    calls = {}
    monkeypatch.setattr(machine, "start_session",
                        lambda name, cwd, **kw: calls.update(kw) or
                        {"ok": True, "name": name, "pid": 1, "cwd": cwd})
    ses.assign(config, agent, t, runtime=ses.MachineRuntime())
    bin_ = calls.get("claude_bin") or ""
    assert "--writable ''" not in bin_ and "--writable \"\"" not in bin_, bin_
    assert str(agent.work_dir) in bin_ or not bin_, bin_


# ── the hook and the sandbox must get the SAME paths ──────────────────

def test_the_ai4science_branch_declares_writable_to_the_hook_too(monkeypatch):
    """Defect 5, and the reason a fully-granted, fully-released task still
    could not write its own file.

    A declared path reaches a session by TWO channels, and they are not the
    same one:

      * the SANDBOX gets `ai4science chat --writable <p>` on the command line;
      * the HOOK gets `PWM_WRITABLE=<p>` in its command prefix, written by
        `ensure_governance_hook` from `start_session(writable=...)`.

    The claude-code branch passed `writable=` and got both. The ai4science
    branch built the `--writable` flags and then called `start_session` WITHOUT
    `writable=`, so the hook was never told. Live: the session stood in
    `/home/grace/p3final`, was launched with `--writable /home/grace/p3final`,
    was released to A1, produced exactly the right file content — and every
    write was still gated, because the boundary that asks had never heard of
    the path.

    `claude_driver` already states the rule this restores: the declared paths go
    to the hook "so the hook and the sandbox draw the same boundary." Two
    boundaries that disagree are one boundary and one blind spot.
    """
    from ai4science.harness.agents.sarsi import session as ses
    import ai4science.harness.agents.machine.sessions as machine

    seen = {}
    monkeypatch.setattr(machine, "start_session",
                        lambda name, cwd, **kw: seen.update(kw) or
                        {"ok": True, "name": name, "pid": 1, "cwd": cwd})

    ses.MachineRuntime().start("s", "/tmp/w", govern=True, ceiling="A1",
                               spec="unified-LLM",
                               writable=["/tmp/w", "/tmp/task"])

    assert seen.get("writable") == ["/tmp/w", "/tmp/task"], (
        "the hook was not told the declared paths: %r" % (seen,))
    # and the sandbox still gets them on the command line
    assert "--writable" in (seen.get("claude_bin") or "")


def test_the_claude_code_branch_is_unchanged(monkeypatch):
    """It already passed them. This pins it so the fix does not swap which
    branch is broken."""
    from ai4science.harness.agents.sarsi import session as ses
    import ai4science.harness.agents.machine.sessions as machine

    seen = {}
    monkeypatch.setattr(machine, "start_session",
                        lambda name, cwd, **kw: seen.update(kw) or
                        {"ok": True, "name": name, "pid": 1, "cwd": cwd})

    ses.MachineRuntime().start("s", "/tmp/w", govern=True, ceiling="A1",
                               spec="claude-code", writable=["/tmp/w"])
    assert seen.get("writable") == ["/tmp/w"]
    # Claude Code has no --writable flag; the hook IS its only boundary
    assert "--writable" not in (seen.get("claude_bin") or "")
