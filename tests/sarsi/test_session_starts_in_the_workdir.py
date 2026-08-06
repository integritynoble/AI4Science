"""`--workdir` says where the work happens. The session should be standing there.

Live on grace, a task declaring `/home/grace/live-brief` started its session in
`~/.sarsi/agents/sarsi-worker/tasks/tsk_6a4bbbb54d` and addressed its own target
as `../../../../../live-brief/report.md`. It worked, because the goal named
absolute paths and `blast` counts a declared root as permitted — but the flag
says *"where the work happens — evidence is gathered from here"* and the work was
happening five levels away from it.

The cost is not tidiness. A session whose cwd is not the work has to be told
every path in full, and a path told in full is a path the owner has to get right
in the goal; a relative one it invents is a path nothing checked.

What must NOT change, and is why this is not a one-line edit:

  * **the plan stays in the task folder.** `plan0.md` is the record and belongs
    with the task, not in a project directory that may be shared, versioned, or
    someone else's. `read_plan` and `collect_plan` look there and keep looking
    there.
  * **so the brief must name it absolutely.** The planning brief said *"I have
    already written an initial plan0.md in this folder"*, which was true only
    while the folder and the cwd were the same thing. A session told to read a
    file that is not where it is standing reads nothing and plans from the goal
    alone — judged against criteria the owner never reviewed.
  * **and the task folder must stay writable.** The session edits `plan0.md` in
    place. A sandbox that only permits the cwd would refuse the one write the
    planning step exists to produce.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["sarsi-worker"]


class Runtime:
    engine = "claude"

    def __init__(self):
        self.started = []

    def start(self, name, cwd, **kw):
        self.started.append({"name": name, "cwd": cwd, **kw})
        return {"ok": True, "name": name, "pid": 4242, "cwd": cwd}

    def send(self, name, text, **kw):
        return {"ok": True}

    def stop(self, name):
        return {"ok": True}


    def set_ceiling(self, name, ceiling):
        """Part of the runtime contract — a double omitting it was hidden by a
        swallowed exception in `release` until that stopped being swallowed."""
        return {"name": name, "ceiling": ceiling}

def _task(config, agent, tmp_path, *, workdir=None):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.create(config, agent, d)
    t = tsk.attach_plan(config, agent, t, pl.draft(d))
    if workdir:
        t.work_root = str(workdir)
        tsk._touch(agent, t, time.time)
    return t


# ── it starts where the work is ───────────────────────────────────────

def test_a_declared_workdir_is_the_session_s_cwd(config, agent, tmp_path):
    work = tmp_path / "project"
    work.mkdir()
    t = _task(config, agent, tmp_path, workdir=work)
    rt = Runtime()
    t = ses.assign(config, agent, t, runtime=rt, installed=lambda: set())
    assert rt.started[0]["cwd"] == str(work.resolve())


def test_and_the_record_says_so(config, agent, tmp_path):
    """`blast` and `spend` read the transcript keyed by this cwd. A record that
    disagreed with where the session ran would send both to the wrong file."""
    work = tmp_path / "project"
    work.mkdir()
    t = _task(config, agent, tmp_path, workdir=work)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    assert t.session["cwd"] == str(work.resolve())


def test_without_one_it_still_starts_in_the_task_folder(config, agent, tmp_path):
    """Unchanged for every task that declares nothing."""
    t = _task(config, agent, tmp_path)
    rt = Runtime()
    t = ses.assign(config, agent, t, runtime=rt, installed=lambda: set())
    assert rt.started[0]["cwd"] == str(tsk.dir_of(agent, t.id))


def test_a_workdir_that_is_not_there_is_not_invented(config, agent, tmp_path):
    """Creating it would turn a typo into a new empty directory the session then
    reports as an empty project. The task folder is the honest fallback."""
    t = _task(config, agent, tmp_path, workdir=tmp_path / "nope")
    rt = Runtime()
    t = ses.assign(config, agent, t, runtime=rt, installed=lambda: set())
    assert rt.started[0]["cwd"] == str(tsk.dir_of(agent, t.id))


# ── and it can still reach its plan ───────────────────────────────────

def test_the_task_folder_is_writable_from_there(config, agent, tmp_path):
    """The session edits plan0.md in place; the plan lives in the task folder,
    which is now somewhere else entirely."""
    work = tmp_path / "project"
    work.mkdir()
    t = _task(config, agent, tmp_path, workdir=work)
    rt = Runtime()
    t = ses.assign(config, agent, t, runtime=rt, installed=lambda: set())
    assert str(tsk.dir_of(agent, t.id)) in (rt.started[0].get("writable") or [])


def test_the_planning_brief_names_the_plan_by_full_path(config, agent, tmp_path):
    """"in this folder" was true only while the cwd and the task folder were the
    same thing. A session told to read a file that is not where it stands reads
    nothing and plans from the goal alone."""
    work = tmp_path / "project"
    work.mkdir()
    t = _task(config, agent, tmp_path, workdir=work)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    brief = t.kickoff_pending or ""
    assert str(tsk.dir_of(agent, t.id) / ses.PLAN_FILE) in brief
    assert "in this folder" not in brief


def test_the_work_brief_names_it_too(config, agent, tmp_path):
    work = tmp_path / "project"
    work.mkdir()
    t = _task(config, agent, tmp_path, workdir=work)
    t.plan_agreed = True
    tsk._touch(agent, t, time.time)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    brief = t.kickoff_pending or ""
    assert str(tsk.dir_of(agent, t.id)) in brief


def test_but_a_task_folder_session_still_reads_naturally(config, agent, tmp_path):
    """No absolute paths where a relative one is correct and shorter."""
    t = _task(config, agent, tmp_path)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    assert "in this folder" in (t.kickoff_pending or "")


# ── evidence is unaffected ────────────────────────────────────────────

def test_both_places_are_still_evidence_roots(config, agent, tmp_path):
    """Moving where it stands must not narrow where its work is looked for."""
    work = tmp_path / "project"
    work.mkdir()
    t = _task(config, agent, tmp_path, workdir=work)
    roots = {str(p) for p in tsk.evidence_roots(agent, t)}
    assert str(work.resolve()) in roots
    assert str(tsk.dir_of(agent, t.id).resolve()) in roots
