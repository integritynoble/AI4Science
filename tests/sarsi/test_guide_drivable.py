"""Steering an interface the loop cannot read.

`deliver_kickoff` already refuses a spec this loop cannot drive, and the reason
is written in its docstring: on the ai4science TUI a brief full of `j`s and `k`s
walked a menu cursor onto **"No, exit"** and killed the session it was
supervising. Every keystroke lands somewhere, and on a menu one option is always
the worst one.

That guard was on **one** of the five paths that type into a session. The other
four go through `guide`, which sent unconditionally:

  * `retry` — the verifier's reason, handed back;
  * `answer` — the owner replying to an escalated question;
  * `sarsi steer` — the owner saying something directly;
  * a goal change, telling a running session the goal moved.

Observed live on grace: `sarsi retry social …` typed a paragraph into an
attended session. It was harmless **only** because that session happened to be
sitting at its prompt. Ten minutes earlier the same session was showing
`Type a number (1-3)`, and ten minutes before that the folder-trust menu whose
second option is *No, exit*. The guard was one screen away from mattering.

So the refusal moves to `guide`, the single place all four pass through:

  * **the author does not matter.** The owner's own words are keystrokes too. A
    guard that waved `by_owner` through would leave `answer` and `steer` — two
    of the four — exactly as exposed.
  * **refuse, do not silently skip.** `deliver_kickoff` returns quietly because
    the loop calls it every pass and an attended session is briefed by hand.
    These four are *commands somebody ran*; a quiet no-op tells the owner their
    retry landed when nothing was delivered.
  * **hand back what to deliver.** The refusal carries the text and the attach
    command, because the owner is now the delivery mechanism.
  * **a refused send costs nothing.** `retry` counted the attempt before typing,
    so three refusals would have exhausted a task that had never once been told
    anything.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (questions as qs, registry as reg,
                                             retry as rty, session as ses,
                                             task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


class _Runtime:
    """Records what was typed, so a test can say *nothing was*."""

    def __init__(self):
        self.sent = []

    def send(self, name, text):
        self.sent.append((name, text))
        return {"ok": True}

    def start(self, *a, **kw):
        return {"name": "s"}

    def stop(self, name):
        return {"ok": True}


def _task(config, agent, *, goal="draft it", failed=True):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    from ai4science.harness.agents.sarsi import plan as pl
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t.session = {"name": f"{agent.id}-live", "cwd": str(tsk.dir_of(agent, t.id))}
    if failed:
        # the shape verifier.parse() writes — `state` / `why`
        t.verdict = {"state": "FAIL", "why": "the contents were never shown"}
    return tsk._touch(agent, t, time.time)


@pytest.fixture
def attended(config):
    """`social` runs the ai4science TUI — the loop cannot read it."""
    agent = config.agents["social"]
    assert not ses.drivable(agent.spec)
    return agent


@pytest.fixture
def drivable(config):
    agent = config.agents["work"]
    assert ses.drivable(agent.spec)
    return agent


# ── the guard itself ──────────────────────────────────────────────────

def test_guide_refuses_a_spec_the_loop_cannot_read(config, attended):
    t = _task(config, attended)
    with pytest.raises(ses.NotDrivable):
        ses.guide(config, attended, t, "fix what the verifier named",
                  runtime=_Runtime())


def test_and_nothing_is_typed(config, attended):
    """The whole point. A refusal that still sent would be a comment."""
    rt = _Runtime()
    t = _task(config, attended)
    with pytest.raises(ses.NotDrivable):
        ses.guide(config, attended, t, "fix it", runtime=rt)
    assert rt.sent == []


def test_the_owners_own_words_are_keystrokes_too(config, attended):
    """A guard that waved `by_owner` through would leave `answer` and `steer`
    — two of the four callers — exactly as exposed. The hazard is the screen,
    not the author."""
    rt = _Runtime()
    t = _task(config, attended)
    with pytest.raises(ses.NotDrivable):
        ses.guide(config, attended, t, "yes, use the staging host",
                  runtime=rt, by_owner=True)
    assert rt.sent == []


def test_the_refusal_hands_back_what_to_deliver(config, attended):
    """The owner is now the delivery mechanism, so it must not swallow the
    text they are meant to deliver."""
    t = _task(config, attended)
    with pytest.raises(ses.NotDrivable) as e:
        ses.guide(config, attended, t, "fix the missing contents",
                  runtime=_Runtime())
    assert "fix the missing contents" in str(e.value)
    assert f"tmux attach -t {t.session['name']}" in str(e.value)


def test_the_refusal_says_which_interface_and_why(config, attended):
    t = _task(config, attended)
    with pytest.raises(ses.NotDrivable) as e:
        ses.guide(config, attended, t, "fix it", runtime=_Runtime())
    said = str(e.value)
    assert attended.spec in said
    assert "cannot read" in said or "cannot be read" in said


def test_a_drivable_session_is_untouched(config, drivable):
    rt = _Runtime()
    t = _task(config, drivable)
    ses.guide(config, drivable, t, "fix it", runtime=rt)
    assert rt.sent == [("work-live", "fix it")]


# ── retry ─────────────────────────────────────────────────────────────

def test_retry_refuses_rather_than_typing_at_an_attended_session(config,
                                                                  attended):
    """Observed live: `sarsi retry social …` typed a paragraph into a session
    the loop is forbidden to type into."""
    rt = _Runtime()
    t = _task(config, attended)
    with pytest.raises(ses.NotDrivable):
        rty.retry(config, attended, t, runtime=rt)
    assert rt.sent == []


def test_a_refused_retry_does_not_burn_an_attempt(config, attended):
    """It counted the attempt before typing. Three refusals would exhaust a
    task that had never once been told anything, and `Exhausted` says "this one
    wants you" — which would be true, for entirely the wrong reason."""
    t = _task(config, attended)
    before = int(t.retries or 0)
    with pytest.raises(ses.NotDrivable):
        rty.retry(config, attended, t, runtime=_Runtime())
    after = [x for x in tsk.all_of(config, attended) if x.id == t.id][0]
    assert int(after.retries or 0) == before


def test_nor_is_a_refused_retry_recorded_as_one(config, attended):
    """The ledger is what `decisions` and `digest` read. An entry saying the
    task was handed back is a claim that something was delivered."""
    from ai4science.harness.agents.sarsi import ledger
    t = _task(config, attended)
    with pytest.raises(ses.NotDrivable):
        rty.retry(config, attended, t, runtime=_Runtime())
    rows = [r for r in ledger.read(config, "reports")
            if r.get("task") == t.id and r.get("state") == "retried"]
    assert rows == []


def test_retry_still_works_where_the_loop_can_read(config, drivable):
    rt = _Runtime()
    t = _task(config, drivable)
    out = rty.retry(config, drivable, t, runtime=rt)
    assert out.retries == 1
    assert rt.sent and "the contents were never shown" in rt.sent[0][1]


def test_the_wheel_being_held_does_not_burn_an_attempt_either(config, drivable):
    """The same ordering bug, on the path that was already guarded: `guide`
    refuses while the owner holds the wheel, and the count had already moved."""
    t = _task(config, drivable)
    t.steering_paused = True                  # the owner took the wheel
    tsk._touch(drivable, t, time.time)
    before = int(t.retries or 0)
    with pytest.raises(ses.OwnerHasTheWheel):
        rty.retry(config, drivable, t, runtime=_Runtime())
    after = [x for x in tsk.all_of(config, drivable) if x.id == t.id][0]
    assert int(after.retries or 0) == before


# ── the verdict, typed back automatically ─────────────────────────────

def _fails(**kw):
    return {"state": "FAIL", "why": "the contents were never shown"}

def test_a_fail_verdict_is_not_typed_at_an_attended_session(config, attended):
    """`verify` types the verifier's reason at the session itself. So the live
    run's `sarsi check social …` had ALREADY typed a paragraph at the attended
    TUI before `retry` did — the same hazard, one command earlier, and nobody
    noticed because that session happened to be at its prompt."""
    rt = _Runtime()
    t = _task(config, attended, failed=False)
    judge = _fails
    ses.verify(config, attended, t, verifier=judge, evidence="a listing",
               runtime=rt)
    assert rt.sent == []


def test_and_the_verdict_is_still_recorded(config, attended):
    """Refusing to type must not cost the verdict — judging is not steering."""
    t = _task(config, attended, failed=False)
    judge = _fails
    out = ses.verify(config, attended, t, verifier=judge, evidence="a listing",
                     runtime=_Runtime())
    assert (out.verdict or {}).get("state") == "FAIL"


def test_and_it_does_not_log_a_correction_nobody_received(config, attended):
    """The module already draws this distinction for a send that failed: "a
    reason that reached no session steered nothing"."""
    from ai4science.harness.agents.sarsi import ledger
    t = _task(config, attended, failed=False)
    judge = _fails
    ses.verify(config, attended, t, verifier=judge, evidence="a listing",
               runtime=_Runtime())
    rows = [r for r in ledger.read(config, "reports") if r.get("task") == t.id]
    assert not any("steered" == r.get("state") for r in rows)


# ── nothing to type at ────────────────────────────────────────────────

def test_a_task_with_no_session_says_so(config, attended):
    """The refusal printed `tmux attach -t ?` for a task that has no session:
    honest about not knowing, and useless — it sends the owner to attach to a
    terminal that does not exist. Having nowhere to deliver is a different fact
    from not being allowed to."""
    t = _task(config, attended)
    t.session = None
    tsk._touch(attended, t, time.time)
    with pytest.raises(ses.NoSession) as e:
        ses.guide(config, attended, t, "fix it", runtime=_Runtime())
    assert "?" not in str(e.value)
    assert "no session" in str(e.value).lower()


def test_it_names_how_to_start_one(config, attended):
    t = _task(config, attended)
    t.session = None
    tsk._touch(attended, t, time.time)
    with pytest.raises(ses.NoSession) as e:
        ses.guide(config, attended, t, "fix it", runtime=_Runtime())
    assert f"sarsi run {attended.id} {t.id}" in str(e.value)


def test_this_holds_for_a_drivable_agent_too(config, drivable):
    """It was silently worse there: `guide` sent to the empty session name and
    reported `sent to ?` — a delivery nobody received, reported as made."""
    rt = _Runtime()
    t = _task(config, drivable)
    t.session = None
    tsk._touch(drivable, t, time.time)
    with pytest.raises(ses.NoSession):
        ses.guide(config, drivable, t, "fix it", runtime=rt)
    assert rt.sent == []


def test_the_answer_path_still_reports_it_the_same_way(config, drivable):
    """`answer` already refused this, with its own `NoSession`. One class, so
    either raise is caught by either name."""
    t = _task(config, drivable, failed=False)
    t.session = None
    tsk._touch(drivable, t, time.time)
    _ask(config, drivable, t)
    with pytest.raises(ses.NoSession):
        qs.answer(config, drivable, t, "which host should I use?", "staging",
                  runtime=_Runtime(), pane=None)
    assert qs.NoSession is ses.NoSession


# ── the chat door ─────────────────────────────────────────────────────

def test_the_chat_door_does_not_type_at_an_attended_session(config, attended):
    """Talking to the agent forwards to its standing task's session. It
    refuses in words rather than raising, the way its siblings here do — this
    answer goes back to a person on Telegram."""
    from ai4science.harness.agents.sarsi import chat
    rt = _Runtime()
    t = _task(config, attended, failed=False)
    out = chat._guided(config, attended, t, "use the staging host", rt)
    assert rt.sent == []
    assert "use the staging host" in out
    assert t.session["name"] in out


def test_the_chat_door_still_steers_what_it_can_read(config, drivable):
    from ai4science.harness.agents.sarsi import chat
    rt = _Runtime()
    t = _task(config, drivable, failed=False)
    chat._guided(config, drivable, t, "use the staging host", rt)
    assert rt.sent == [("work-live", "use the staging host")]


# ── the two remaining typing paths ────────────────────────────────────

def test_release_does_not_retype_the_kickoff_at_an_attended_session(config,
                                                                     attended):
    """`release` re-sends the brief when handing the wheel back. Quiet, not
    raised: raising would make `release` fail outright on an attended agent,
    and the owner briefs it by hand exactly as `deliver_kickoff` intends."""
    rt = _Runtime()
    t = _task(config, attended, failed=False)
    ses.release(config, attended, t, runtime=rt)
    assert rt.sent == []


def test_a_bad_plan_is_not_typed_back_at_an_attended_session(config, attended):
    """`collect_plan` types "that plan cannot be used" at the session. Same
    keystrokes, same unknown screen."""
    rt = _Runtime()
    t = _task(config, attended, failed=False)
    (tsk.dir_of(attended, t.id) / ses.PLAN_FILE).write_text(
        "# a plan with no criterion\n\n## Phase 1 — do it\n")
    ses.collect_plan(config, attended, t, runtime=rt, session_idle=True)
    assert rt.sent == []


# ── a goal change ─────────────────────────────────────────────────────

def test_changing_the_goal_still_works_on_an_attended_task(config, attended):
    """The goal change is a record edit; telling the running session is a
    courtesy on top. Letting the refusal escape would mean an attended agent's
    goal could not be changed at all while it held a session."""
    from ai4science.harness.agents.sarsi import chat
    t = _task(config, attended, failed=False)
    out = chat._goal(config, attended, t, "draft two posts instead",
                     runtime=_Runtime())
    after = [x for x in tsk.all_of(config, attended) if x.id == t.id][0]
    assert after.goal == "draft two posts instead"
    assert "deliver" in out.lower() or "yourself" in out.lower()


def test_and_it_does_not_claim_the_session_was_told(config, attended):
    """`its running session has been told` about a session nothing reached."""
    from ai4science.harness.agents.sarsi import chat
    t = _task(config, attended, failed=False)
    out = chat._goal(config, attended, t, "draft two posts instead",
                     runtime=_Runtime())
    assert "has been told" not in out


# ── answer ────────────────────────────────────────────────────────────

def _ask(config, agent, task, text="which host should I use?"):
    """An escalation is a ledger entry, the way the loop writes one."""
    from ai4science.harness.agents.sarsi import ledger
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": qs.ASKED,
                   "evidence": [f"Q: {text}",
                                "escalated: the plan does not settle it"]})


def test_answering_an_attended_session_is_refused(config, attended):
    rt = _Runtime()
    t = _task(config, attended, failed=False)
    _ask(config, attended, t)
    with pytest.raises(ses.NotDrivable):
        qs.answer(config, attended, t, "which host should I use?", "staging",
                  runtime=rt, pane=None)
    assert rt.sent == []


def test_and_the_question_stays_open(config, attended):
    """It was not answered. A question closed by a refused delivery is one the
    owner believes they have dealt with."""
    t = _task(config, attended, failed=False)
    _ask(config, attended, t)
    with pytest.raises(ses.NotDrivable):
        qs.answer(config, attended, t, "which host should I use?", "staging",
                  runtime=_Runtime(), pane=None)
    assert [q.text for q in qs.open_of(config, attended)] == \
        ["which host should I use?"]


def test_answering_still_works_where_the_loop_can_read(config, drivable):
    rt = _Runtime()
    t = _task(config, drivable, failed=False)
    _ask(config, drivable, t)
    qs.answer(config, drivable, t, "which host should I use?", "staging",
              runtime=rt, pane=None)
    assert rt.sent and "staging" in rt.sent[0][1]
    assert qs.open_of(config, drivable) == []
