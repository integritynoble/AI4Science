"""Blast radius — what the plan said it would touch, against what it touched.

The plan already declares a working directory. This turns *"it said it would
only touch the export folder"* into something checked rather than trusted: the
session's own transcript records every `Write` and `Edit` with its `file_path`,
so what was written is **read**, not inferred.

The whole value rests on one refusal:

  **`Bash` is opaque, and opaque is never reported as clean.** A transcript
  showing 40 shell commands and 2 writes tells us about the 2. Answering "no
  files outside the radius" on that evidence would be a false assurance about
  the 40 — precisely the kind of confident wrong this system keeps producing
  when it treats unknown as zero.

So the report has three parts, always: what was inside, what escaped, and **how
much could not be checked at all**.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (blast, plan as pl, registry as reg,
                                             task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"),
                  root=tmp_path / "state")
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["work"]


def _task(config, agent, root, *, also=()):
    plan = pl.Plan(goal="g", work_root=str(root), may_touch=list(also),
                   phases=[pl.Phase(title="x", verified_when="y")])
    d = worker.Directive(agent_id=agent.id, goal="g")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), plan)
    t.session = {"name": "work-0001", "pid": 1, "cwd": str(root)}
    tsk._touch(agent, t, __import__("time").time)
    return t


def _acts(*entries):
    def read(cwd):
        return list(entries)
    return read


def _write(path):
    return {"name": "Write", "input": {"file_path": path}}


def _edit(path):
    return {"name": "Edit", "input": {"file_path": path}}


def _bash(command="ls"):
    return {"name": "Bash", "input": {"command": command}}


# ── the declaration ───────────────────────────────────────────────────

def test_the_working_directory_is_in_the_radius(config, agent, tmp_path):
    """It is added to the radius, not swapped for it: the task's own folder is
    where the session runs, and writing where it runs is not an escape. Live,
    `abraham` wrote into its task folder and was told the file did not exist."""
    t = _task(config, agent, tmp_path / "work")
    roots = blast.declared(agent, t)
    assert (tmp_path / "work").resolve() in roots
    assert tsk.dir_of(agent, t.id).resolve() in roots


def test_a_plan_can_declare_more_than_one_path(config, agent, tmp_path):
    t = _task(config, agent, tmp_path / "work", also=[str(tmp_path / "out")])
    assert (tmp_path / "out").resolve() in blast.declared(agent, t)


def test_the_declaration_survives_a_render_and_reparse(tmp_path):
    original = pl.Plan(goal="g", work_root=str(tmp_path),
                       may_touch=[f"{tmp_path}/out", f"{tmp_path}/logs"],
                       phases=[pl.Phase(title="x", verified_when="y")])
    assert list(pl.parse(original.render()).may_touch) == [f"{tmp_path}/out",
                                                           f"{tmp_path}/logs"]


# ── what it touched ───────────────────────────────────────────────────

def test_a_write_inside_the_radius_is_reported_as_inside(config, agent, tmp_path):
    root = tmp_path / "work"
    t = _task(config, agent, root)
    got = blast.check(config, agent, t, acts=_acts(_write(str(root / "a.txt"))))
    assert got.inside == [str(root / "a.txt")]
    assert got.outside == []
    assert got.escaped is False


def test_a_write_outside_the_radius_is_named(config, agent, tmp_path):
    root = tmp_path / "work"
    t = _task(config, agent, root)
    got = blast.check(config, agent, t,
                      acts=_acts(_write(str(tmp_path / "elsewhere.txt"))))
    assert got.outside == [str(tmp_path / "elsewhere.txt")]
    assert got.escaped is True


def test_an_edit_counts_the_same_as_a_write(config, agent, tmp_path):
    root = tmp_path / "work"
    t = _task(config, agent, root)
    got = blast.check(config, agent, t,
                      acts=_acts(_edit(str(tmp_path / "elsewhere.txt"))))
    assert got.escaped is True


def test_a_second_declared_path_is_inside(config, agent, tmp_path):
    root, out = tmp_path / "work", tmp_path / "out"
    t = _task(config, agent, root, also=[str(out)])
    got = blast.check(config, agent, t, acts=_acts(_write(str(out / "r.csv"))))
    assert got.escaped is False


def test_reading_a_file_is_not_touching_it(config, agent, tmp_path):
    """A radius is about what was CHANGED. Counting reads would flag every
    session that looked at its own source."""
    root = tmp_path / "work"
    t = _task(config, agent, root)
    got = blast.check(config, agent, t, acts=_acts(
        {"name": "Read", "input": {"file_path": "/etc/hosts"}}))
    assert got.outside == []


# ── opaque is never clean ─────────────────────────────────────────────

def test_shell_commands_are_counted_as_unchecked(config, agent, tmp_path):
    """A transcript showing 40 shell commands and 2 writes tells us about the
    2. Reporting 'nothing escaped' would be a false assurance about the 40.

    `ls` is no longer among them: a command PROVEN read-only cannot have
    changed anything, so counting it as unobserved claimed the report might be
    missing a write that could not have happened. `cp` and the redirect can
    both write and are still unchecked — which is the assurance this test is
    actually about."""
    root = tmp_path / "work"
    t = _task(config, agent, root)
    got = blast.check(config, agent, t,
                      acts=_acts(_bash("cp x /tmp/y"), _bash("ls"),
                                 _bash("echo hi > /tmp/z"),
                                 _write(str(root / "a.txt"))))
    assert got.unchecked == 2
    assert got.read_only == 1
    assert "could not" in got.summary.lower() or "unchecked" in got.summary.lower()


def test_a_clean_report_with_unchecked_commands_does_not_claim_clean(
        config, agent, tmp_path):
    root = tmp_path / "work"
    t = _task(config, agent, root)
    got = blast.check(config, agent, t, acts=_acts(_bash("rm -rf /tmp/x")))
    assert got.escaped is False               # nothing OBSERVED escaped …
    assert got.confident is False             # … and it does not claim clean


def test_with_nothing_opaque_it_can_say_so(config, agent, tmp_path):
    root = tmp_path / "work"
    t = _task(config, agent, root)
    got = blast.check(config, agent, t, acts=_acts(_write(str(root / "a.txt"))))
    assert got.confident is True


def test_no_transcript_is_not_a_clean_bill(config, agent, tmp_path):
    def broken(cwd):
        raise FileNotFoundError("no transcript")

    t = _task(config, agent, tmp_path / "work")
    got = blast.check(config, agent, t, acts=broken)
    assert got.confident is False
    assert "no record" in got.summary.lower() or "could not" in got.summary.lower()


# ── a task with no declaration ────────────────────────────────────────

def test_a_task_with_no_working_directory_uses_its_own_folder(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="g")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    assert blast.declared(agent, t) == [tsk.dir_of(agent, t.id).resolve()]


# ── it shows up where the owner reads ─────────────────────────────────

def test_why_reports_an_escape(config, agent, tmp_path):
    from ai4science.harness.agents.sarsi import why as wy
    root = tmp_path / "work"
    root.mkdir(parents=True)
    t = _task(config, agent, root)
    (root / ".transcript-stub").write_text("")
    out = wy.explain(config, agent, t,
                     acts=_acts(_write(str(tmp_path / "escaped.txt"))))
    assert "escaped.txt" in out


# ── a command that cannot have written anything ───────────────────────

def _bash(cmd, key="command"):
    return {"name": "Bash", "input": {key: cmd}}


def test_a_read_only_command_is_not_counted_as_unchecked(config, agent, tmp_path):
    """Every run today closed on the same line — `2 shell command(s) could not
    be checked` — and every one of those commands was the session verifying its
    own work: `wc -w checklist.md`, `ls -la`, `grep -c`. A command that cannot
    change anything has nothing to vouch for. Counting it as unobserved says
    the report might be missing a write that could not have happened.

    Judged by `permissions.is_read_only_bash` — the same conservative
    classifier that decides what may run without asking. What it cannot PROVE
    read-only still counts as unchecked, so this can only ever shrink the
    number by things it is certain about."""
    t = _task(config, agent, tmp_path)
    got = blast.check(config, agent, t,
                      acts=lambda cwd: [_bash("wc -w checklist.md"),
                                        _bash("ls -la"),
                                        _bash("grep -c '^' notes.md")])
    assert got.unchecked == 0


def test_and_that_is_a_clean_bill(config, agent, tmp_path):
    """The point of the change: a session that wrote through the tool and only
    LOOKED with the shell can now be vouched for."""
    t = _task(config, agent, tmp_path)
    root = str(tmp_path)
    got = blast.check(config, agent, t,
                      acts=lambda cwd: [{"name": "Write",
                                         "input": {"file_path": root + "/a.md"}},
                                        _bash("wc -w a.md")])
    assert got.confident is True
    assert "not a clean bill" not in got.summary


def test_anything_that_might_write_is_still_unchecked(config, agent, tmp_path):
    """The conservatism is the whole guarantee."""
    for cmd in ("cat > out.md <<'EOF'", "mkdir -p /tmp/x", "python3 run.py",
                "rm -rf /tmp/x", "curl -o f https://example.com",
                "echo hi > note.md"):
        t = _task(config, agent, tmp_path)
        got = blast.check(config, agent, t, acts=lambda cwd: [_bash(cmd)])
        assert got.unchecked == 1, cmd


def test_the_harness_spells_the_argument_differently(config, agent, tmp_path):
    """Claude Code records `command`, the ai4science harness records `cmd`.
    Reading one key would leave every attended agent's shell calls unchecked —
    the kind of detail that has been wrong three times today."""
    t = _task(config, agent, tmp_path)
    got = blast.check(config, agent, t,
                      acts=lambda cwd: [_bash("ls -la", key="cmd")])
    assert got.unchecked == 0


def test_a_bash_call_with_no_command_at_all_is_unchecked(config, agent, tmp_path):
    """Nothing to classify is not the same as nothing to worry about."""
    t = _task(config, agent, tmp_path)
    got = blast.check(config, agent, t,
                      acts=lambda cwd: [{"name": "Bash", "input": {}}])
    assert got.unchecked == 1


def test_the_read_only_ones_are_still_reported(config, agent, tmp_path):
    """Dropping them silently would leave a reader unable to tell a session
    that ran fifty commands from one that ran none."""
    t = _task(config, agent, tmp_path)
    got = blast.check(config, agent, t,
                      acts=lambda cwd: [_bash("ls"), _bash("wc -l a"),
                                        _bash("cat b")])
    assert got.read_only == 3
    assert "3" in got.summary and "read-only" in got.summary
