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
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.deliver_kickoff(config, agent, t, runtime=rt)
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
    # the owner accepts the sketch deliberately
    t = ses.collect_plan(config, agent, t, runtime=rt, accept_seed=True)
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
    kickoff = ses.deliver_kickoff(config, agent, t, runtime=rt) and rt.sent[0]
    assert "plan0.md" in kickoff
    assert "Verified when:" in kickoff
    assert "Permissions needed" in kickoff


def test_the_planning_kickoff_says_to_stop_after_planning(config, agent):
    """Otherwise it drafts a plan and then does the work nobody granted."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.deliver_kickoff(config, agent, t, runtime=rt)
    assert "stop" in rt.sent[0].lower()


def test_the_task_is_planning_not_running(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert t.state == tsk.PLANNING


def test_the_goal_and_scope_reach_the_planner(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.deliver_kickoff(config, agent, t, runtime=rt)
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


# ── the kickoff is delivered when the session can receive it ──────────

def test_assign_does_not_type_into_a_session_that_is_still_booting(config, agent):
    """social's live run: `assign` typed the kickoff microseconds after
    `tmux new-session`, Claude Code was still starting, and the text was lost.
    The session then sat there asking "What would you like me to work on?" while
    the worker believed it had been told."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.sent == []                      # nothing typed at a booting session
    assert t.kickoff_pending                  # it is owed one, and says so


def test_the_pending_kickoff_is_the_planning_one(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert "plan0.md" in t.kickoff_pending
    assert "improve" in t.kickoff_pending.lower()


def test_delivering_it_types_it(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.deliver_kickoff(config, agent, t, runtime=rt)
    assert rt.sent and "plan0.md" in rt.sent[0]


def test_it_is_not_retyped_once_it_has_been_seen(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.deliver_kickoff(config, agent, t, runtime=rt)
    seen = ses._kickoff_marker(rt.sent[0])          # what the session shows back
    t = ses.deliver_kickoff(config, agent, t, runtime=rt, screen=seen)
    ses.deliver_kickoff(config, agent, t, runtime=rt, screen=seen)
    assert len(rt.sent) == 1


# ── an untouched seed is never adopted on the agent's say-so ──────────

def test_an_untouched_seed_is_not_adopted_even_when_the_session_is_quiet(config, agent):
    """It was, and social's run went to `ready` holding a plan that said
    "(provisional — no criterion was given)". A quiet session is not the same as
    a session that has planned."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    after = ses.collect_plan(config, agent, t, runtime=rt, session_idle=True)
    assert after.state == tsk.PLANNING


def test_the_owner_may_accept_the_seed_deliberately(config, agent):
    """If the session will not plan, that is the owner's call to make — and it
    is an explicit act, not something a quiet pass decides for them."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    after = ses.collect_plan(config, agent, t, runtime=rt, accept_seed=True)
    assert after.state in (tsk.READY, tsk.AWAITING_GRANT)


# ── delivery is confirmed by SEEING it, not by having sent it ─────────

def test_the_kickoff_stays_pending_until_it_is_seen_on_screen(config, agent):
    """grace's run: the kickoff was typed while Claude Code was still showing
    its startup banner, went nowhere, and the worker cleared `pending` anyway —
    then spent the rest of the run believing the session had been told."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.deliver_kickoff(config, agent, t, runtime=rt, screen="")
    assert tsk.get(config, agent, t.id).kickoff_pending is not None


def test_seeing_it_clears_it(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    marker = ses._kickoff_marker(t.kickoff_pending)
    t = ses.deliver_kickoff(config, agent, t, runtime=rt, screen=f"❯ {marker}")
    assert tsk.get(config, agent, t.id).kickoff_pending is None


def test_it_is_resent_when_it_did_not_land(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    for _ in range(2):
        t = ses.deliver_kickoff(config, agent, t, runtime=rt, screen="")
    assert len(rt.sent) == 2


def test_it_gives_up_and_says_so_rather_than_typing_forever(config, agent):
    """A loop that retypes the same instruction every pass is how a session
    ends up with six copies of its own brief."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    for _ in range(6):
        t = ses.deliver_kickoff(config, agent, t, runtime=rt, screen="")
    assert len(rt.sent) <= ses.MAX_KICKOFF_TRIES
    assert t.kickoff_undelivered is True


def test_the_planning_brief_says_how_to_look_around_at_a0(config, agent):
    """grace's run stopped on `ls -la`, because planning runs at A0 and a shell
    command is not a read. Widening the allowlist to let a loop approve shell
    commands would undo the drop; telling the session which tools it HAS at A0
    costs nothing and keeps the authority model intact."""
    t = _task(config, agent)
    brief = ses.planning_kickoff(config, agent, t)
    assert "A0" in brief
    assert "shell" in brief.lower() or "command" in brief.lower()
    assert "read" in brief.lower()
