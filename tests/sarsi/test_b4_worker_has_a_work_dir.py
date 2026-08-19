"""5-B4, the workspace half: a worker HAS somewhere to work.

    **Workspace.** Today `--workdir` is a flag, and until 2026-08-07 the folder
    it named was not even writable by the session. A worker should *have* a
    workspace.

Two names, deliberately kept apart. This codebase already has
`Agent.workspace` and it means **W_name** — mission, plan, decisions, where the
owner log lives. That is what the worker *knows*. What was missing is where its
tasks *work*, so this is `Agent.work_dir`. Using one word for both is the
"two things, one name" failure that has already cost this project a day.

The default is per-WORKER, not per-task, because that is what the ask means: a
desk persists across the jobs done at it, and files left from the last task are
usually the point. A task that needs isolation still passes `--workdir`, which
overrides — explicit beats implicit, as it did before.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import registry as reg, task as tsk, worker as wk


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


# ── the worker has one ────────────────────────────────────────────────

def test_a_worker_has_a_work_dir(config):
    a = config.agents["sarsi-worker"]
    assert a.work_dir
    assert a.work_dir.name != "workspace", (
        "work_dir must not collide with W_name, which is what the worker KNOWS")


def test_it_is_created_with_the_others(config):
    a = config.agents["sarsi-worker"]
    assert a.work_dir.is_dir(), "ensure_dirs did not make it"


def test_it_is_per_worker_not_shared(config):
    a, b = config.agents["sarsi-worker"], config.agents["jobs"]
    assert a.work_dir != b.work_dir


# ── and a task uses it without being told ─────────────────────────────

def test_a_task_with_no_workdir_gets_the_workers(config):
    """The whole point. The owner should not have to remember `--workdir`."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="write a solver"))
    assert t.work_root == str(a.work_dir), t.work_root


def test_an_explicit_workdir_still_wins(config):
    """Explicit beats implicit. A default that cannot be overridden is not a
    default, it is a decision taken from the owner."""
    a = config.agents["sarsi-worker"]
    d = tsk.dir_of(a, "x").parent / "somewhere-else"
    d.mkdir(parents=True, exist_ok=True)
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t.work_root = str(d)
    assert t.work_root == str(d)


def test_the_work_dir_is_declared_writable(config):
    """A workspace the session cannot write is not a workspace. This is exactly
    what defect 4 was: the declared directory reached the sandbox and the
    session still could not write it."""
    from ai4science.harness.agents.sarsi import session as ses
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    seen = {}

    class _RT:
        engine = "claude"
        def start(self, name, cwd, *, govern, ceiling, env=None,
                  spec="claude-code", writable=None):
            seen["cwd"], seen["writable"] = cwd, list(writable or [])
            return {"ok": True, "name": name}
        def send(self, name, text):
            return {"ok": True}

    ses.assign(config, a, t, runtime=_RT(), installed=lambda: set())
    assert seen["cwd"] == str(a.work_dir.resolve())
    assert str(a.work_dir.resolve()) in seen["writable"], seen["writable"]


def test_attaching_a_plan_that_names_no_directory_keeps_the_desk(config):
    """The defect the LIVE loop found and the unit tests did not.

    `tsk.create` sets the desk; `attach_plan` then assigned
    `task.work_root = plan.work_root` unconditionally, and a drafted plan
    declares none — so every task made through the REPL, which drafts
    immediately, came out with `work_root = None`. Tested at `create()` it
    passed; typed at a keyboard it did not.

    A plan that says nothing about a working directory is not a plan that says
    "nowhere".
    """
    from ai4science.harness.agents.sarsi import plan as pl
    a = config.agents["sarsi-worker"]
    d = wk.Directive(agent_id=a.id, goal="write a solver")
    t = tsk.create(config, a, d)
    t = tsk.attach_plan(config, a, t, pl.draft(d))
    assert t.work_root == str(a.work_dir), t.work_root


def test_but_a_plan_that_names_one_still_wins(config):
    """The plan is where a working directory is declared and agreed. When it
    names one, that is the answer."""
    from ai4science.harness.agents.sarsi import plan as pl
    a = config.agents["sarsi-worker"]
    d = wk.Directive(agent_id=a.id, goal="g")
    t = tsk.create(config, a, d)
    import dataclasses
    plan = dataclasses.replace(pl.draft(d), work_root="/tmp/declared-elsewhere")
    t = tsk.attach_plan(config, a, t, plan)
    assert t.work_root == "/tmp/declared-elsewhere"
