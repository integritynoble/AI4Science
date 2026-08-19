"""`attention` — "is anything waiting on me?"

Everything that went wrong on the live runs went wrong **silently**. Catching it
took a human watching `tmux`: a gate the loop had no rule for, a first-run trust
dialog, a session that finished having written nothing. A worker that cannot
answer *"is anything waiting on you?"* makes the owner the monitor, which is the
job the worker exists to remove.

Every input already exists — gates on the pane, `awaiting` on the task, the
retry count, the stale flag, the session record. Nothing read them together, and
that was the whole defect.

Three properties:

  * **it is about the OWNER, not about progress.** A busy session is not on this
    list. Only things that will not move until a human does something.
  * **a gate is reported with the actual command.** "A gate is waiting" tells the
    owner to go and look; the command tells them whether they need to.
  * **it never invents a blockage it cannot see.** A session whose pane cannot
    be read is reported as *unreadable*, not as idle and not as fine.
"""
import pytest

from ai4science.harness.agents.sarsi import (attention as att, plan as pl,
                                             registry as reg, session as ses,
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


@pytest.fixture
def agent(config):
    return config.agents["sarsi-worker"]


class FakeRuntime:
    engine = "claude"

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None,
              writable=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


class Pane:
    """A pane that answers per session name, and knows which exist.

    Returns **None** for a name it does not have, which is what the real
    `TmuxPane.capture` does — it raised, so every test below that says "the
    pane is simply gone" was in fact exercising the exception path, and the
    gone path had no coverage at all. The two are different answers now:
    None is gone, an exception is nobody could look.
    """

    def __init__(self, screens=None):
        self.screens = screens or {}

    def capture(self, name):
        return self.screens.get(name)

    def send(self, name, text):
        pass

    def key(self, name, key):
        pass


GATE = """\
 Bash command

   rm -f result.json && python3 gaptv.py

 Do you want to proceed?
 ❯ 1. Yes
   2. No
"""

BUSY = "* Reticulating splines… (esc to interrupt)"


def _task(config, agent, goal="finish the export", secrets=()):
    d = worker.Directive(agent_id=agent.id, goal=goal,
                         requires_secrets=list(secrets))
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.start(config, agent, t)


def _with_session(config, agent, goal="finish the export"):
    # `installed` is injected for the same reason `live` is (see below): left
    # as None it asks the REAL agent registry, and whether `unified-LLM` is
    # installed on the machine running the tests walks into the assertion.
    return ses.assign(config, agent, _task(config, agent, goal),
                      runtime=FakeRuntime(), installed=lambda: set())


# ── nothing waiting ───────────────────────────────────────────────────
#
# `live` is injected in every test here, not only the unclaimed ones: left as
# None it asks the REAL tmux, and a session someone else started on this
# machine walks into the assertion. A live `sarsi-worker-…` did exactly that,
# and made this whole file red on the machine that runs the fleet.

def test_an_empty_worker_needs_nothing(config, agent):
    assert att.needs(config, agent, pane=Pane(), live=lambda: set()).items == []


def test_a_busy_session_is_not_asking_for_you(config, agent):
    """Progress is not a blockage. Listing it teaches the owner to ignore
    the list."""
    t = _with_session(config, agent)
    pane = Pane({t.session["name"]: BUSY})
    assert att.needs(config, agent, pane=pane,
                     live=lambda: {t.session["name"]}).items == []


# ── a gate, with the command ──────────────────────────────────────────

def test_a_gate_is_reported(config, agent):
    t = _with_session(config, agent)
    got = att.needs(config, agent, pane=Pane({t.session["name"]: GATE}),
                    live=lambda: {t.session["name"]})
    assert [i.kind for i in got.items] == ["gate"]
    assert got.items[0].task_id == t.id


def test_the_gate_carries_the_actual_command(config, agent):
    """'A gate is waiting' sends the owner to look; the command tells them
    whether they need to."""
    t = _with_session(config, agent)
    got = att.needs(config, agent, pane=Pane({t.session["name"]: GATE}),
                    live=lambda: {t.session["name"]})
    assert "rm -f result.json" in got.items[0].detail


# ── the things that never reach a pane at all ─────────────────────────

def test_an_ungranted_permission_is_waiting_on_you(config, agent):
    _task(config, agent, "read my mail", secrets=["mail.read"])
    got = att.needs(config, agent, pane=Pane(), live=lambda: set())
    assert [i.kind for i in got.items] == ["grant"]
    assert "mail.read" in got.items[0].detail


def test_an_exhausted_retry_is_waiting_on_you(config, agent):
    from ai4science.harness.agents.sarsi import retry as rty
    t = _task(config, agent)
    t.retries = rty.MAX_RETRIES
    t.verdict = {"verdict": "FAIL", "reason": "export.csv still has 0 rows"}
    tsk._touch(agent, t, __import__("time").time)
    got = att.needs(config, agent, pane=Pane(), live=lambda: set())
    assert [i.kind for i in got.items] == ["exhausted"]
    assert "0 rows" in got.items[0].detail


def test_a_stale_plan_is_waiting_on_you(config, agent):
    t = _task(config, agent)
    t.plan_stale = True
    tsk._touch(agent, t, __import__("time").time)
    assert [i.kind for i in att.needs(config, agent, pane=Pane(),
                                      live=lambda: set()).items] == ["stale"]


def test_an_undelivered_kickoff_is_waiting_on_you(config, agent):
    t = _with_session(config, agent)
    t.kickoff_undelivered = True
    tsk._touch(agent, t, __import__("time").time)
    kinds = [i.kind for i in att.needs(config, agent,
                                       pane=Pane({t.session["name"]: BUSY}),
                                       live=lambda: {t.session["name"]}).items]
    assert "undelivered" in kinds


# ── the record disagreeing with the machine ───────────────────────────

def test_a_record_pointing_at_a_dead_terminal_is_reported(config, agent):
    """Sessions outlive the process that started them. Reporting state that
    was true when it was written is how the board lies."""
    t = _with_session(config, agent)
    got = att.needs(config, agent, pane=Pane({}),     # the pane is simply gone
                    live=lambda: set())
    assert [i.kind for i in got.items] == ["dead-session"]
    assert t.session["name"] in got.items[0].detail


def test_an_unreadable_pane_is_never_reported_as_fine(config, agent):
    """Still the point of this test, and still true. What changed is WHICH
    thing it is reported as: `dead-session` claimed the terminal was gone, and
    nobody had looked. `unreadable` says so."""
    class Broken:
        def capture(self, name):
            raise OSError("tmux is not running")

    def broken():
        raise OSError("tmux is not running")

    t = _with_session(config, agent)
    got = att.needs(config, agent, pane=Broken(), live=broken)
    assert got.items and got.items[0].kind == "unreadable"
    assert "is not there" not in got.items[0].detail


# ── ordering and shape ────────────────────────────────────────────────

def test_the_most_blocking_thing_is_first(config, agent):
    """A gate stops work now; a stale plan stops the next decision."""
    stale = _task(config, agent, "job one")
    stale.plan_stale = True
    tsk._touch(agent, stale, __import__("time").time)
    gated = _with_session(config, agent, "job two")
    got = att.needs(config, agent, pane=Pane({gated.session["name"]: GATE}),
                    live=lambda: {gated.session["name"]})
    assert [i.kind for i in got.items] == ["gate", "stale"]


def test_it_summarises_in_one_line(config, agent):
    t = _with_session(config, agent)
    got = att.needs(config, agent, pane=Pane({t.session["name"]: GATE}),
                    live=lambda: {t.session["name"]})
    assert "1" in got.summary and "gate" in got.summary.lower()


def test_the_summary_says_so_when_nothing_is_waiting(config, agent):
    assert "nothing" in att.needs(config, agent, pane=Pane(),
                                  live=lambda: set()).summary.lower()


def test_an_archived_task_never_asks_for_attention(config, agent):
    t = _task(config, agent)
    t.plan_stale = True
    tsk.archive(config, agent, t)
    assert att.needs(config, agent, pane=Pane(), live=lambda: set()).items == []


# ── across every worker ───────────────────────────────────────────────

def test_the_fleet_view_names_which_agent(config):
    from ai4science.harness.agents.sarsi import registry as _reg
    work, social = config.agents["sarsi-worker"], config.agents["social"]
    _task(config, work, "read my mail", secrets=["mail.read"])
    _task(config, social, "draft the thread", secrets=["x.post"])
    # `live` is injected: without it this asks the REAL tmux, and a session
    # someone else started on this machine walks into the assertion. A live
    # `sarsi-worker-…` did exactly that.
    rows = att.across(config, pane=Pane(), live=lambda: set())
    assert {r.agent_id for r in rows.items} == {"sarsi-worker", "social"}


def test_the_manager_holds_no_tasks_and_is_not_scanned(config):
    """It drives nothing, so it can be blocked on nothing."""
    rows = att.across(config, pane=Pane(), live=lambda: set())
    assert all(r.agent_id != "sarsi-machine" for r in rows.items)


# ── an orphan: the terminal outliving the task ────────────────────────

def test_a_session_still_running_after_the_task_ended_is_an_orphan(config, agent):
    """Observed on the other fleet: a session sat running for two hours after
    its task had FAILED, holding a grant at A2, and nothing reported it.

    A dead-session is a record pointing at nothing. An orphan is the reverse —
    a live terminal nothing is steering — and it is the more dangerous of the
    two, because it still holds whatever the task was granted.
    """
    t = _with_session(config, agent)
    t = tsk.finish(config, agent, t,
                   verdict={"state": "PASS", "why": "all criteria met"})
    got = att.needs(config, agent, pane=Pane({t.session["name"]: BUSY}),
                    live=lambda: {t.session["name"]})
    assert [i.kind for i in got.items] == ["orphan"]
    assert t.session["name"] in got.items[0].detail


def test_an_orphan_is_reported_after_a_failed_task_too(config, agent):
    t = _with_session(config, agent)
    t.state = tsk.OFF
    tsk._touch(agent, t, __import__("time").time)
    kinds = [i.kind for i in att.needs(config, agent,
                                       pane=Pane({t.session["name"]: BUSY}),
                                       live=lambda: {t.session["name"]}).items]
    assert kinds == ["orphan"]


def test_the_orphan_says_how_to_close_it(config, agent):
    t = _with_session(config, agent)
    t = tsk.finish(config, agent, t, verdict={"state": "PASS", "why": "done"})
    got = att.needs(config, agent, pane=Pane({t.session["name"]: BUSY}),
                    live=lambda: {t.session["name"]})
    assert f"stop {agent.id}" in got.items[0].action


def test_a_running_task_with_a_live_session_is_not_an_orphan(config, agent):
    """That is just work happening."""
    t = _with_session(config, agent)
    assert att.needs(config, agent, pane=Pane({t.session["name"]: BUSY}),
                     live=lambda: {t.session["name"]}).items == []


def test_a_finished_task_whose_terminal_is_gone_is_not_an_orphan(config, agent):
    """Nothing is running, so nothing is holding anything. Closing the record
    is tidiness, not safety — and attention is for what needs the owner."""
    t = _with_session(config, agent)
    t = tsk.finish(config, agent, t, verdict={"state": "PASS", "why": "done"})
    assert att.needs(config, agent, pane=Pane({}),
                     live=lambda: set()).items == []


def test_an_orphan_outranks_a_stale_plan(config, agent):
    t = _with_session(config, agent)
    t = tsk.finish(config, agent, t, verdict={"state": "PASS", "why": "done"})
    t.plan_stale = True
    tsk._touch(agent, t, __import__("time").time)
    kinds = [i.kind for i in att.needs(config, agent,
                                       pane=Pane({t.session["name"]: BUSY}),
                                       live=lambda: {t.session["name"]}).items]
    assert kinds.index("orphan") < kinds.index("stale")


# ── a terminal no task claims ─────────────────────────────────────────

def test_a_live_terminal_no_task_claims_is_waiting_on_you(config, agent):
    """The dangerous direction: a dead-session record makes the board look
    busier than the machine. This is the reverse — something is running, still
    holding whatever it was granted, and the board shows NOTHING at all.
    """
    got = att.needs(config, agent, pane=Pane(), live=lambda: {"sarsi-worker-9zz9"})
    assert [i.kind for i in got.items] == ["unclaimed"]
    assert "sarsi-worker-9zz9" in got.items[0].detail


def test_it_says_how_to_close_one(config, agent):
    got = att.needs(config, agent, pane=Pane(), live=lambda: {"sarsi-worker-9zz9"})
    assert "tmux" in got.items[0].action


def test_another_agents_terminal_is_not_this_agents_problem(config, agent):
    got = att.needs(config, agent, pane=Pane(), live=lambda: {"social-1234"})
    assert got.items == []


def test_a_terminal_a_task_claims_is_not_unclaimed(config, agent):
    t = _with_session(config, agent)
    got = att.needs(config, agent, pane=Pane({t.session["name"]: BUSY}),
                    live=lambda: {t.session["name"]})
    assert [i.kind for i in got.items] == []


def test_an_archived_tasks_terminal_is_claimed_by_it(config, agent):
    """Calling it unclaimed would send the owner hunting for a task that is
    sitting right there in the archive."""
    t = _with_session(config, agent)
    name = t.session["name"]
    tsk.archive(config, agent, t)
    got = att.needs(config, agent, pane=Pane({name: BUSY}), live=lambda: {name})
    assert not [i for i in got.items if i.kind == "unclaimed"]


def test_tmux_being_unreachable_reports_no_unclaimed_terminals(config, agent):
    """It cannot see them, so it must not claim there are none OR invent some.
    `enter` is where an unreachable tmux is reported."""
    def broken():
        raise OSError("tmux is not running")

    assert att.needs(config, agent, pane=Pane(), live=broken).items == []


def test_an_unclaimed_terminal_outranks_a_stale_plan(config, agent):
    t = _task(config, agent)
    t.plan_stale = True
    tsk._touch(agent, t, __import__("time").time)
    got = att.needs(config, agent, pane=Pane(), live=lambda: {"sarsi-worker-9zz9"})
    kinds = [i.kind for i in got.items]
    assert kinds.index("unclaimed") < kinds.index("stale")


def test_the_fleet_view_carries_it_too(config):
    rows = att.across(config, pane=Pane(), live=lambda: {"sarsi-worker-9zz9",
                                                         "social-4242"})
    assert {(i.agent_id, i.kind) for i in rows.items} == {
        ("sarsi-worker", "unclaimed"), ("social", "unclaimed")}
