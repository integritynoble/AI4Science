"""`TSK` — a worker holds several tasks, each with its own plan.

Slice 2b's observations: one worker holds several at once; a task over the
concurrency limit **says so** rather than looking idle; and a plan declaring
permissions sits in `awaiting-grant` until the owner grants.

A task never disappears — turning one off keeps its record, which is what makes
it resumable, and a refusal is an outcome rather than an error.
"""
import pytest

from ai4science.harness.agents.sarsi import plan as pl, registry as reg, task, worker


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
    return config.agents["work"]


def _directive(goal="tidy the report folder", **kw):
    return worker.Directive(agent_id="work", goal=goal, **kw)


def _plan(permissions=()):
    return pl.Plan(goal="tidy the report folder",
                   phases=[pl.Phase(title="sort", verified_when="the folder lists 0 stray files")],
                   permissions=list(permissions))


# ── several tasks, all visible ────────────────────────────────────────

def test_a_worker_holds_several_tasks_at_once(config, agent):
    for i in range(3):
        task.create(config, agent, _directive(goal=f"job {i}"))
    assert len(task.all_of(config, agent)) == 3


def test_a_task_is_visible_from_the_moment_it_exists(config, agent):
    """A task the owner cannot see is a task the owner cannot stop."""
    t = task.create(config, agent, _directive())
    assert t.state == task.PLANNING
    assert [x.id for x in task.all_of(config, agent)] == [t.id]


def test_tasks_of_one_agent_are_not_anothers(config):
    task.create(config, config.agents["work"], _directive())
    assert task.all_of(config, config.agents["abraham"]) == []


def test_a_task_survives_a_restart(config, agent):
    t = task.create(config, agent, _directive())
    assert task.get(config, agent, t.id).goal == "tidy the report folder"


# ── the plan attaches to the task ─────────────────────────────────────

def test_attaching_a_plan_writes_plan0_beside_the_task(config, agent):
    t = task.create(config, agent, _directive())
    t = task.attach_plan(config, agent, t, _plan())
    assert (task.dir_of(agent, t.id) / "plan0.md").exists()
    assert t.criteria == ["the folder lists 0 stray files"]


def test_a_plan_with_no_permissions_makes_the_task_ready(config, agent):
    t = task.attach_plan(config, agent, task.create(config, agent, _directive()), _plan())
    assert t.state == task.READY


def test_a_plan_declaring_permissions_waits_for_the_owner(config, agent):
    t = task.attach_plan(config, agent, task.create(config, agent, _directive()),
                         _plan(permissions=["write /home/me/reports"]))
    assert t.state == task.AWAITING_GRANT
    assert t.awaiting == ["write /home/me/reports"]


def test_granting_what_the_plan_declared_makes_it_ready(config, agent):
    t = task.attach_plan(config, agent, task.create(config, agent, _directive()),
                         _plan(permissions=["write /home/me/reports"]))
    t = task.grant(config, agent, t, "write /home/me/reports")
    assert t.state == task.READY and t.awaiting == []


def test_granting_something_else_does_not_release_the_task(config, agent):
    """A grant answers the permission it names, and no other."""
    t = task.attach_plan(config, agent, task.create(config, agent, _directive()),
                         _plan(permissions=["write /home/me/reports"]))
    t = task.grant(config, agent, t, "write /tmp")
    assert t.state == task.AWAITING_GRANT


# ── concurrency says so ───────────────────────────────────────────────

def test_over_the_limit_a_task_says_it_is_waiting_for_a_slot(config, agent):
    """Never silently queued: an unstarted task that looks like a running one
    is the NOM failure wearing a different hat."""
    agent.max_concurrent_tasks = 2
    ready = []
    for i in range(3):
        t = task.attach_plan(config, agent, task.create(config, agent, _directive(goal=f"job {i}")),
                             _plan())
        ready.append(task.start(config, agent, t))
    assert [t.state for t in ready] == [task.RUNNING, task.RUNNING, task.READY]
    assert ready[-1].blocked_by == "concurrency"


def test_a_finished_task_frees_its_slot(config, agent):
    agent.max_concurrent_tasks = 1
    a = task.start(config, agent,
                   task.attach_plan(config, agent, task.create(config, agent, _directive()), _plan()))
    b = task.attach_plan(config, agent, task.create(config, agent, _directive(goal="second")), _plan())
    assert task.start(config, agent, b).state == task.READY
    task.finish(config, agent, a, verdict={"state": "PASS", "by": "verifier"})
    assert task.start(config, agent, b).state == task.RUNNING


def test_a_task_cannot_start_before_its_permissions_are_granted(config, agent):
    t = task.attach_plan(config, agent, task.create(config, agent, _directive()),
                         _plan(permissions=["write /home/me/reports"]))
    assert task.start(config, agent, t).state == task.AWAITING_GRANT


# ── states are outcomes, and records are kept ─────────────────────────

def test_turning_a_task_off_keeps_its_record(config, agent):
    t = task.start(config, agent,
                   task.attach_plan(config, agent, task.create(config, agent, _directive()), _plan()))
    t = task.turn_off(config, agent, t)
    assert t.state == task.OFF
    assert task.get(config, agent, t.id) is not None      # resumable, not erased


def test_a_task_turned_off_can_be_resumed(config, agent):
    t = task.start(config, agent,
                   task.attach_plan(config, agent, task.create(config, agent, _directive()), _plan()))
    t = task.resume(config, agent, task.turn_off(config, agent, t))
    assert t.state == task.RUNNING


def test_finishing_without_a_verdict_is_refused(config, agent):
    """`verified` is the verifier's word, not the worker's."""
    t = task.start(config, agent,
                   task.attach_plan(config, agent, task.create(config, agent, _directive()), _plan()))
    with pytest.raises(worker.UnverifiedClaim):
        task.finish(config, agent, t, verdict=None)


def test_a_finished_task_records_the_verdict(config, agent):
    t = task.start(config, agent,
                   task.attach_plan(config, agent, task.create(config, agent, _directive()), _plan()))
    t = task.finish(config, agent, t, verdict={"state": "PASS", "by": "verifier"})
    assert t.state == task.VERIFIED and t.verdict["state"] == "PASS"


def test_the_manager_holds_no_tasks(config):
    with pytest.raises(worker.NotAWorker):
        task.create(config, config.agents["sarsi-machine"],
                    worker.Directive(agent_id="sarsi-machine", goal="do a thing"))
