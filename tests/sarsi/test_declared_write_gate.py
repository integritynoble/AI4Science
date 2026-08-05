"""A write inside the declared paths is one the owner already authorised.

Every live run today ended the same way: correct work, and the loop stopped at

    Create file
    /home/grace/live-final/win.md
    …
    Do you want to create win.md?
    ❯ 1. Yes
      2. Yes, allow all edits in live-final/ during this session
      3. No

That directory is the one the task declared, the owner granted the permission
its plan named, and `release` raised the ceiling. `blast` already treats those
paths as *"paths the task is allowed to write"*, and the harness sandbox already
permits them — `PermissionGate` allows `[workspace] + writable_roots`, which
`assign` fills from the same list. The only thing still asking is Claude Code's
hook, and the answer it is asking for is one the owner has already given.

So this is not the loop inventing authority; it is the loop applying authority
that exists. Which makes it exactly the shape of `deletion.permitted` — the one
destructive gate the loop may answer — and it is built the same way: **refusing
is the default and every path out of it is explicit.**

Adversarial first. The four that matter:

  * **outside the declared paths** — including the prefix trap, where
    `/x/live-jobs-evil` shares six characters with `/x/live-jobs` and is not
    inside it. Compared as resolved paths, never as strings.
  * **before release** — the ceiling is still A0 and the owner has not acted.
    Nothing has been authorised yet, so there is nothing to apply.
  * **a path the gate does not state in full** — `Do you want to create
    summary.md?` names a basename, and live that basename belonged to
    `../../../../../live-retire/summary.md`. A file located by guessing is a
    file approved by guessing.
  * **the wider option** — *"and allow all edits during this session"* is a
    standing grant for everything that follows, which is not what the owner
    gave and not what this may take.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import writes


def _gate(header="Create file", path="/work/out.md", question="create out.md",
          wider=True):
    lines = [
        "● Write(out.md)",
        "",
        f" {header}",
        f" {path}",
        "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌",
        "  1 hello",
        "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌",
        f" Do you want to {question}?",
        " ❯ 1. Yes",
    ]
    if wider:
        lines.append("   2. Yes, allow all edits in work/ during this session")
        lines.append("   3. No")
    else:
        lines.append("   2. No")
    return "\n".join(lines) + "\n"


@pytest.fixture
def roots(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    return [root]


# ── outside the declared paths ────────────────────────────────────────

def test_a_path_outside_the_declared_roots_is_refused(tmp_path, roots):
    other = tmp_path / "elsewhere"
    other.mkdir()
    ok, why = writes.permitted(_gate(path=str(other / "x.md")),
                               roots=roots, cwd=roots[0], released=True)
    assert ok is False
    assert "outside" in why.lower()


def test_the_prefix_trap(tmp_path, roots):
    """`/x/work-evil` shares its first characters with `/x/work` and is not
    inside it. Compared as resolved paths, never as strings."""
    evil = tmp_path / "work-evil"
    evil.mkdir()
    ok, _ = writes.permitted(_gate(path=str(evil / "x.md")),
                             roots=roots, cwd=roots[0], released=True)
    assert ok is False


def test_climbing_out_with_dot_dot(roots):
    ok, _ = writes.permitted(_gate(path="../../etc/passwd"),
                             roots=roots, cwd=roots[0], released=True)
    assert ok is False


def test_an_absolute_system_path(roots):
    ok, _ = writes.permitted(_gate(path="/etc/passwd"),
                             roots=roots, cwd=roots[0], released=True)
    assert ok is False


def test_the_root_itself_is_not_a_file_to_write(roots):
    ok, _ = writes.permitted(_gate(path=str(roots[0])),
                             roots=roots, cwd=roots[0], released=True)
    assert ok is False


# ── before the owner acted ────────────────────────────────────────────

def test_an_unreleased_task_is_refused(roots):
    """The ceiling is still A0 and nothing has been granted. There is no
    authority to apply."""
    ok, why = writes.permitted(_gate(), roots=roots, cwd=roots[0],
                               released=False)
    assert ok is False
    assert "release" in why.lower()


def test_and_no_declared_roots_at_all_is_refused(tmp_path):
    ok, _ = writes.permitted(_gate(), roots=[], cwd=tmp_path, released=True)
    assert ok is False


# ── a path that is not stated in full ─────────────────────────────────

def test_a_gate_naming_only_a_basename_is_refused(roots):
    """Live, `Do you want to create summary.md?` belonged to
    `../../../../../live-retire/summary.md`. A file located by guessing is a
    file approved by guessing."""
    screen = (" Do you want to create summary.md?\n ❯ 1. Yes\n   2. No\n")
    ok, why = writes.permitted(screen, roots=roots, cwd=roots[0], released=True)
    assert ok is False
    assert "which file" in why.lower() or "path" in why.lower()


def test_a_gate_with_no_write_header_is_refused(roots):
    ok, _ = writes.permitted("some narration\n❯ 1. Yes\n  2. No\n",
                             roots=roots, cwd=roots[0], released=True)
    assert ok is False


def test_two_paths_in_one_gate_are_refused(roots):
    """If it cannot be read as one file, it is not read at all."""
    screen = (" Create file\n /work/a.md\n Create file\n /elsewhere/b.md\n"
              " Do you want to proceed?\n ❯ 1. Yes\n   2. No\n")
    ok, _ = writes.permitted(screen, roots=roots, cwd=roots[0], released=True)
    assert ok is False


# ── never the standing grant ──────────────────────────────────────────

def test_the_answer_is_the_narrow_yes(roots):
    """Option 2 is *"allow all edits during this session"* — a standing grant
    for everything that follows, which is not what the owner gave."""
    ok, _ = writes.permitted(_gate(path=str(roots[0] / "out.md")),
                             roots=roots, cwd=roots[0], released=True)
    assert ok is True
    assert writes.ANSWER == "1"


def test_a_gate_whose_first_option_is_the_wider_one_is_refused(roots):
    """If `1` is not the narrow yes, pressing `1` takes the standing grant."""
    screen = (f" Create file\n {roots[0] / 'out.md'}\n"
              " Do you want to create out.md?\n"
              " ❯ 1. Yes, allow all edits in work/ during this session\n"
              "   2. Yes\n   3. No\n")
    ok, why = writes.permitted(screen, roots=roots, cwd=roots[0], released=True)
    assert ok is False
    assert "standing" in why.lower() or "all edits" in why.lower()


# ── what it is for ────────────────────────────────────────────────────

def test_a_new_file_inside_the_declared_root(roots):
    ok, why = writes.permitted(_gate(path=str(roots[0] / "out.md")),
                               roots=roots, cwd=roots[0], released=True)
    assert ok is True, why
    assert str(roots[0]) in why


def test_a_relative_path_resolved_against_the_session_cwd(roots):
    ok, _ = writes.permitted(_gate(path="out.md"), roots=roots, cwd=roots[0],
                             released=True)
    assert ok is True


def test_an_edit_to_an_existing_file(roots):
    (roots[0] / "notes.md").write_text("x")
    ok, _ = writes.permitted(_gate(header="Edit file",
                                   path=str(roots[0] / "notes.md"),
                                   question="make this edit to notes.md"),
                             roots=roots, cwd=roots[0], released=True)
    assert ok is True


def test_a_second_declared_root_counts_too(tmp_path, roots):
    """The task folder and the working directory are both declared."""
    task_dir = tmp_path / "tsk_abc"
    task_dir.mkdir()
    ok, _ = writes.permitted(_gate(path=str(task_dir / "plan0.md")),
                             roots=roots + [task_dir], cwd=roots[0],
                             released=True)
    assert ok is True


# ── through the operator ──────────────────────────────────────────────

def test_the_loop_answers_it_on_a_released_task(tmp_path, monkeypatch):
    """Inert unless `_gate` consults it with the task's own declared paths."""
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.sarsi import (operator as op, plan as pl,
                                                 registry as reg,
                                                 session as ses, task as tsk,
                                                 worker as wk)
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    a = c.agents["sarsi-worker"]
    work = tmp_path / "project"
    work.mkdir()

    d = wk.Directive(agent_id=a.id, goal="write the report")
    t = tsk.create(c, a, d)
    (tsk.dir_of(a, t.id) / "plan0.md").write_text(
        "# g\n\n## Phase 1 — do it\nVerified when: out.md exists\n")
    t = tsk.attach_plan(c, a, t, pl.parse(
        "# g\n\n## Phase 1 — do it\nVerified when: out.md exists\n"))
    t.work_root = str(work)
    t.plan_agreed = True

    class RT:
        engine = "claude"
        def start(self, name, cwd, **kw):
            return {"ok": True, "name": name, "pid": 1, "cwd": cwd}
        def send(self, name, text, **kw):
            return {"ok": True}
        def stop(self, name):
            return {"ok": True}

    t = ses.assign(c, a, t, runtime=RT(), installed=lambda: set())
    t.kickoff_pending = None
    t.released_at = time.time()
    t.work_started_at = time.time()
    t.state = tsk.RUNNING
    tsk._touch(a, t, time.time)

    class Pane:
        def __init__(self):
            self.sent = []
        def capture(self, name):
            return _gate(path=str(work / "out.md"))
        def send(self, name, text):
            self.sent.append(text)
            return {"ok": True}
        def key(self, name, key):
            return {"ok": True}

    pane = Pane()
    act = op.tick(c, a, t, pane=pane, now=time.time)
    assert act.kind == "answered", act
    assert pane.sent == ["1"]


def test_but_not_one_outside_the_declared_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.sarsi import (operator as op, plan as pl,
                                                 registry as reg,
                                                 session as ses, task as tsk,
                                                 worker as wk)
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    a = c.agents["sarsi-worker"]
    work = tmp_path / "project"
    work.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    d = wk.Directive(agent_id=a.id, goal="write the report")
    t = tsk.create(c, a, d)
    body = "# g\n\n## Phase 1 — do it\nVerified when: out.md exists\n"
    (tsk.dir_of(a, t.id) / "plan0.md").write_text(body)
    t = tsk.attach_plan(c, a, t, pl.parse(body))
    t.work_root = str(work)
    t.plan_agreed = True

    class RT:
        engine = "claude"
        def start(self, name, cwd, **kw):
            return {"ok": True, "name": name, "pid": 1, "cwd": cwd}
        def send(self, name, text, **kw):
            return {"ok": True}
        def stop(self, name):
            return {"ok": True}

    t = ses.assign(c, a, t, runtime=RT(), installed=lambda: set())
    t.kickoff_pending = None
    t.released_at = time.time()
    t.work_started_at = time.time()
    t.state = tsk.RUNNING
    tsk._touch(a, t, time.time)

    class Pane:
        def __init__(self):
            self.sent = []
        def capture(self, name):
            return _gate(path=str(outside / "x.md"))
        def send(self, name, text):
            self.sent.append(text)
            return {"ok": True}
        def key(self, name, key):
            return {"ok": True}

    pane = Pane()
    act = op.tick(c, a, t, pane=pane, now=time.time)
    assert act.kind == "abstained", act
    assert pane.sent == []
    assert "outside" in act.detail.lower()
