"""The plan is made **between** the worker and the session.

The worker has no model and no view of the repo; `sarsi-claude` has both. So the
worker does not write the plan — it **guides the session to write it**, reads it
back, and holds the task until the owner has seen what it declared.

That ordering is the whole design problem. If the session drafts the plan, the
session has already started before anyone knows what it needs — and the worst
moment to ask for a permission is halfway through unattended work. So:

  1. the session is asked for a **plan and nothing else**, and told to stop;
  2. the worker reads `plan0.md` back off disk;
  3. the task waits at **`awaiting-grant`** until the owner grants and edits;
  4. only then is the session released to work its earliest incomplete phase.

And there is a ladder of who may drive, with the owner at the top:

| | who | beats |
|---|---|---|
| 1 | the **owner**, in interact | everything — the worker stands down entirely |
| 2 | the **owner**, guiding | the worker's own steering |
| 3 | the **worker**, guiding | its own automatic composer |
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk, worker)


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


class FakeRuntime:
    engine = "claude"

    def __init__(self):
        self.started, self.sent = [], []

    def start(self, name, cwd, *, govern, ceiling, env=None):
        self.started.append(name)
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}


def _task(config, agent, goal="finish the export"):
    """A task with NO plan — the state the worker starts from."""
    d = worker.Directive(agent_id=agent.id, goal=goal, scope=["/home/me/reports"])
    return tsk.create(config, agent, d)


GOOD_PLAN = """\
# finish the export

## Phase 1 — drain the queue
Verified when: the queue length reads 0

## Phase 2 — write it
Verified when: export.csv exists and has 1,204 rows

## Permissions needed
- write /home/me/reports
"""

NO_CRITERION = """\
# finish the export

## Phase 1 — do the thing
I'll figure it out as I go.

## Permissions needed
- none
"""


# ── the worker seeds it, and they finish it together ──────────────────

def test_the_worker_writes_an_initial_plan_before_asking(config, agent):
    """The seed anchors the plan to what the owner actually asked for — the
    goal, the scope, the tools and secrets the directive declared — and leaves
    something usable if the session produces nothing at all."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    seed = (tsk.dir_of(agent, t.id) / "plan0.md").read_text()
    assert "finish the export" in seed
    assert "Verified when:" in seed
    assert "## Permissions needed" in seed


def test_the_seed_carries_what_the_directive_declared(config, agent):
    from ai4science.harness.agents.sarsi import vault
    vault.put(config, "mail.read", "x")
    d = worker.Directive(agent_id=agent.id, goal="read the mail",
                         scope=["/home/me/reports"], requires_secrets=["mail.read"])
    t = tsk.create(config, agent, d)
    rt = FakeRuntime()
    t = ses.assign(config, agent, t, runtime=rt, vault_prompt=lambda **kw: "yes")
    seed = (tsk.dir_of(agent, t.id) / "plan0.md").read_text()
    assert "mail.read" in seed and "/home/me/reports" in seed


def test_the_session_is_asked_to_improve_the_plan_not_invent_one(config, agent):
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    kickoff = rt.sent[0].lower()
    assert "already" in kickoff or "initial" in kickoff
    assert "improve" in kickoff or "sharpen" in kickoff


def test_the_session_rewriting_it_is_what_gets_adopted(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, GOOD_PLAN)                  # the session's version
    t = ses.collect_plan(config, agent, t, runtime=rt)
    assert t.criteria[0] == "the queue length reads 0"


def test_a_plan_the_session_never_touched_is_flagged_as_still_the_seed(config, agent):
    """So a thin stub is never mistaken for a considered plan."""
    from ai4science.harness.agents.sarsi import ledger
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    # the session stopped without improving it
    t = ses.collect_plan(config, agent, t, runtime=rt, session_idle=True)
    row = [r for r in ledger.read(config, "reports") if r.get("state") == "planned"][-1]
    assert row["unchanged"] is True


def test_a_plan_the_session_improved_is_not_flagged(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, GOOD_PLAN)
    ses.collect_plan(config, agent, t, runtime=rt)
    row = [r for r in ledger.read(config, "reports") if r.get("state") == "planned"][-1]
    assert row["unchanged"] is False


# ── the worker asks for a plan, not for the work ──────────────────────

def test_a_task_with_no_plan_is_asked_to_plan_first(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    kickoff = rt.sent[0]
    assert "plan0.md" in kickoff
    assert "Verified when:" in kickoff
    assert "Permissions needed" in kickoff


def test_the_planning_kickoff_says_to_stop_after_planning(config, agent):
    """Otherwise it drafts a plan and then does the work nobody granted."""
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert "stop" in rt.sent[0].lower()


def test_the_task_is_planning_not_running(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert t.state == tsk.PLANNING


def test_the_goal_and_scope_reach_the_planner(config, agent):
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert "finish the export" in rt.sent[0]
    assert "/home/me/reports" in rt.sent[0]


# ── reading the plan back ─────────────────────────────────────────────

def _write_plan(agent, t, text):
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(text)


def test_the_worker_collects_the_plan_the_session_wrote(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, GOOD_PLAN)
    t = ses.collect_plan(config, agent, t, runtime=rt)
    assert t.criteria == ["the queue length reads 0",
                          "export.csv exists and has 1,204 rows"]


def test_what_the_plan_declared_holds_the_task_for_the_owner(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, GOOD_PLAN)
    t = ses.collect_plan(config, agent, t, runtime=rt)
    assert t.state == tsk.AWAITING_GRANT
    assert t.awaiting == ["write /home/me/reports"]


def test_a_plan_needing_nothing_is_ready_but_not_running(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, GOOD_PLAN.replace("- write /home/me/reports", "- none"))
    t = ses.collect_plan(config, agent, t, runtime=rt)
    assert t.state == tsk.READY


def test_no_plan_yet_collects_nothing_and_waits(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert ses.collect_plan(config, agent, t, runtime=rt).state == tsk.PLANNING


# ── a bad plan is sent back, not accepted ─────────────────────────────

def test_a_phase_with_no_criterion_is_sent_back_to_the_session(config, agent):
    """Accepting it would leave the agent that did the work as the only grader."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, NO_CRITERION)
    before = len(rt.sent)
    t = ses.collect_plan(config, agent, t, runtime=rt)
    assert t.state == tsk.PLANNING
    assert "Verified when" in rt.sent[-1]
    assert len(rt.sent) > before


# ── releasing it to work ──────────────────────────────────────────────

def test_a_granted_task_is_released_with_the_phase_named(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, GOOD_PLAN)
    t = ses.collect_plan(config, agent, t, runtime=rt)
    t = tsk.grant(config, agent, t, "write /home/me/reports")
    t = ses.release(config, agent, t, runtime=rt)
    assert t.state == tsk.RUNNING
    assert "drain the queue" in rt.sent[-1]


def test_an_ungranted_task_is_not_released(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _write_plan(agent, t, GOOD_PLAN)
    t = ses.collect_plan(config, agent, t, runtime=rt)
    before = len(rt.sent)
    with pytest.raises(ses.NotReady, match="write /home/me/reports"):
        ses.release(config, agent, t, runtime=rt)
    assert len(rt.sent) == before


# ── who drives ────────────────────────────────────────────────────────

def test_the_worker_may_guide_its_own_session(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.guide(config, agent, t, "put the criteria in terms of row counts",
              runtime=rt)
    assert rt.sent[-1] == "put the criteria in terms of row counts"


def test_the_owner_at_the_wheel_outranks_the_worker(config, agent):
    """Interact is the top of the ladder: the worker stands down entirely."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t.steering_paused = True
    before = len(rt.sent)
    with pytest.raises(ses.OwnerHasTheWheel):
        ses.guide(config, agent, t, "do it my way", runtime=rt)
    assert len(rt.sent) == before


def test_who_drives_names_the_owner_when_they_hold_it(config, agent):
    t = _task(config, agent)
    t.steering_paused = True
    assert ses.who_drives(t) == "owner"


def test_who_drives_names_the_worker_otherwise(config, agent):
    assert ses.who_drives(_task(config, agent)) == "worker"


def test_the_owner_guiding_is_not_blocked_by_the_worker(config, agent):
    """Guided is the owner's word arriving through the worker's path — it is
    never held back because the worker was mid-steer."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.guide(config, agent, t, "use the staging host", runtime=rt, by_owner=True)
    assert rt.sent[-1] == "use the staging host"


def test_even_paused_the_owners_own_guidance_goes_through(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t.steering_paused = True
    ses.guide(config, agent, t, "carry on with this", runtime=rt, by_owner=True)
    assert rt.sent[-1] == "carry on with this"
