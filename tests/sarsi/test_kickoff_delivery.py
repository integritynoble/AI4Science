"""The brief is typed at a screen that can take it, and a new session gets a
fresh count.

Live on grace, three supervise runs in a row reported *"the session is not
taking its brief"*. I sent the same text by hand with `tmux send-keys` and it
landed instantly, so the session was never the problem. The record said why:

    tsk_c8bcc7d118  kickoff_tries=3  kickoff_undelivered=True

All three tries were spent during the run where `start_session` had reported a
session that did not exist — there was no pane, so nothing could have been
typed. When the session was restarted for real, `assign` set a new
`kickoff_pending` and left the counter alone, so the loop declared the brief
undeliverable **before sending a single keystroke into the session that
existed**.

Two things are wrong here and they are not the same thing:

  * **a count of failures belongs to the session that failed.** Carrying it
    into a new one reports the past as though it were the present, which is the
    one thing every reporter in this system is built not to do.

  * **the planning branch types blind.** The work branch has guarded this since
    it was written — `if not _busy(screen) and _gate(screen) is None` — and the
    planning branch, which is where *every* task starts, has no guard at all.
    Keystrokes at a modal are not a brief: the text is discarded and the Enter
    answers whatever option is highlighted. A try spent that way was never an
    attempt to deliver anything, and counting it brings the owner three passes
    closer to a report that says the session is refusing its brief when the
    session has not yet been asked.
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
    """A session that starts, and records what was typed into it."""
    engine = "claude"

    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    def start(self, name, cwd, **kw):
        if not self.ok:
            return {"ok": False, "reason": "claude did not stay up"}
        return {"ok": True, "name": name, "pid": 4242, "cwd": cwd}

    def send(self, name, text, **kw):
        self.sent.append(text)
        return {"ok": True}

    def stop(self, name):
        return {"ok": True}


def _task(config, agent, goal="write the summary"):
    d = wk.Directive(agent_id=agent.id, goal=goal)
    t = tsk.create(config, agent, d)
    return tsk.attach_plan(config, agent, t, pl.draft(d))


# ── a new session starts with a clean count ───────────────────────────

def test_a_new_session_does_not_inherit_the_old_one_s_failures(config, agent):
    """The live case, in miniature."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    t.kickoff_tries = ses.MAX_KICKOFF_TRIES
    t.kickoff_undelivered = True
    tsk._touch(agent, t, time.time)

    t.session = None                        # what `stop` leaves behind
    t.state = tsk.RUNNING
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())

    assert t.kickoff_tries == 0
    assert t.kickoff_undelivered is False


def test_and_the_new_session_is_actually_typed_at(config, agent):
    """The count resetting is only worth anything if a brief follows it."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    t.kickoff_tries = ses.MAX_KICKOFF_TRIES
    t.session = None
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())

    rt = Runtime()
    ses.deliver_kickoff(config, agent, t, runtime=rt, screen="❯ ", now=time.time)
    assert rt.sent, "a fresh session was declared undeliverable unsent"


def test_a_session_that_would_not_start_leaves_no_count_behind(config, agent):
    """`assign` raising must not leave a task carrying tries for a session that
    never existed — that is exactly how the live one got to three."""
    t = _task(config, agent)
    with pytest.raises(ses.CouldNotStart):
        ses.assign(config, agent, t, runtime=Runtime(ok=False),
                   installed=lambda: set())
    assert t.kickoff_tries == 0


# ── and it is not typed at a screen that cannot take it ───────────────

def _screen_gate():
    return ("● Reading 1 file…\n"
            " Bash command\n\n"
            "   ls -la /tmp\n"
            "   List directory contents\n\n"
            " Do you want to proceed?\n"
            " ❯ 1. Yes\n"
            "   2. No\n")


def _screen_busy():
    """What the loop actually recognises as working — `esc to interrupt`.

    My first version of this invented a plausible-looking busy pane without
    that line and passed for the wrong reason. `_BUSY` is one marker wide, and
    a captured pane whose tail has scrolled past it reads as idle; that is a
    real gap, but it is not this one, and widening the matcher to make a
    fixture pass is how a filter gets calibrated on something never observed.
    """
    return ("● Reading 1 file, listing 1 directory…\n"
            "  ⎿  $ ls -la /tmp\n\n"
            "  ⏵⏵ esc to interrupt\n")


def _screen_ready():
    return ("╭─── Claude Code ───╮\n│ Welcome back! │\n╰───╯\n\n"
            "────────────\n❯ \n────────────\n  ⏸ manual mode on\n")


def test_it_is_not_typed_while_a_gate_is_on_screen(config, agent):
    """Text at a modal is discarded and the Enter answers the highlighted
    option — the loop would be voting on a permission prompt with the brief."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    rt = Runtime()
    ses.deliver_kickoff(config, agent, t, runtime=rt, screen=_screen_gate(),
                        now=time.time)
    assert rt.sent == []


def test_nor_while_the_session_is_working(config, agent):
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    rt = Runtime()
    ses.deliver_kickoff(config, agent, t, runtime=rt, screen=_screen_busy(),
                        now=time.time)
    assert rt.sent == []


def test_a_pass_that_could_not_type_does_not_spend_a_try(config, agent):
    """The count is of attempts to deliver. A pass that correctly declined to
    type made no attempt, and spending a try for it walks the owner toward
    'the session is refusing its brief' about a session never asked."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    before = t.kickoff_tries
    t = ses.deliver_kickoff(config, agent, t, runtime=Runtime(),
                            screen=_screen_gate(), now=time.time)
    assert t.kickoff_tries == before
    assert t.kickoff_undelivered is False


def test_but_a_ready_screen_is_typed_at(config, agent):
    """The guard must not be so wide that nothing is ever delivered."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    rt = Runtime()
    t = ses.deliver_kickoff(config, agent, t, runtime=rt,
                            screen=_screen_ready(), now=time.time)
    assert rt.sent
    assert t.kickoff_tries == 1


def test_a_delivered_brief_still_clears_when_it_is_seen(config, agent):
    """Unchanged: seeing it on screen is what counts as delivered."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    marker = ses._kickoff_marker(t.kickoff_pending)
    t = ses.deliver_kickoff(config, agent, t, runtime=Runtime(),
                            screen=f"❯ \n{marker}", now=time.time)
    assert t.kickoff_pending is None


# ── a send that never reached tmux is not a refusal ───────────────────

class DeadRuntime(Runtime):
    """tmux has no such session — what the live run was actually hitting."""
    def send(self, name, text, **kw):
        self.sent.append(text)
        return {"ok": False, "reason": f"no session {name!r}"}


def test_a_send_that_could_not_reach_a_session_is_not_a_spent_try(config, agent):
    """This is what produced the live report. The pane was gone, every send
    returned ok:False, `deliver_kickoff` discarded the result and counted three
    tries anyway — so the owner was told the session was not taking its brief
    when there was no session to take it."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    rt = DeadRuntime()
    for _ in range(ses.MAX_KICKOFF_TRIES + 2):
        t = ses.deliver_kickoff(config, agent, t, runtime=rt,
                                screen=_screen_ready(), now=time.time)
    assert t.kickoff_undelivered is False
    assert t.kickoff_tries == 0


def test_and_it_says_the_session_is_gone_rather_than_unwilling(config, agent):
    """Two different things the owner would do something different about."""
    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    t = ses.deliver_kickoff(config, agent, t, runtime=DeadRuntime(),
                            screen=_screen_ready(), now=time.time)
    assert t.kickoff_unreachable is True


# ── an undelivered brief must not bury a plan already written ─────────

def test_a_plan_is_still_collected_when_the_brief_looks_undelivered(config, agent):
    """Live: the session read its brief, wrote a real plan with a proper
    `Verified when:` line — and the loop reported `undelivered` three passes
    running and never collected it. The brief is judged delivered by seeing a
    marker on screen, and the marker scrolls away as soon as the session starts
    working, so the evidence of delivery is destroyed BY delivery succeeding.

    `undelivered` returned before `collect_plan` ran, so the exhausted counter
    became a permanent block on the one step planning exists to reach. Whatever
    the brief's delivery status, a plan that is on disk is a fact, and a report
    about typing must not outrank it."""
    from ai4science.harness.agents.sarsi import operator as op

    t = _task(config, agent)
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    t.kickoff_tries = ses.MAX_KICKOFF_TRIES
    t.kickoff_undelivered = True
    tsk._touch(agent, t, time.time)

    # what the session actually wrote, at the path the plan is read from
    (tsk.dir_of(agent, t.id) / ses.PLAN_FILE).write_text(
        "# goal\n\n## Phase 1 — write the file\n"
        "Verified when: out.txt exists and contains 130.0\n")

    class Pane:
        def capture(self, name):
            return "❯ \n"
        def send(self, name, text):
            return {"ok": True}
        def key(self, name, key):
            return {"ok": True}

    act = op.tick(config, agent, t, pane=Pane(), now=time.time)
    assert act.kind != "undelivered", act
    after = tsk.get(config, agent, t.id)
    assert after.criteria, "the plan on disk was never collected"
