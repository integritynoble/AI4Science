"""Per-phase verdicts — so "which phase is it on" has an answer.

Until now the number did not exist. `session.kickoff` and `composer.compose`
both said *"earliest incomplete phase"* and handed over `plan.phases[0]` every
time, on every steer, regardless of what had been done. A two-phase plan whose
first phase was finished still told the session it was starting at phase 1.

A phase is complete when **the verifier said so about that phase**. Not when the
session claims it, not when the loop moves on. That single rule is what makes the
number trustworthy, and it forces the rest:

  * **judging a phase judges its criterion, not all of them.** Otherwise "phase
    1 passed" means "everything passed", and the number is decoration.
  * **the task is verified when every phase is** — a per-phase pass is not a
    task-level pass.
  * **editing a phase's criterion clears that phase's verdict.** It was judged
    against a standard that no longer exists; keeping the PASS would carry a
    verdict about a question nobody asked any more.
  * **moving the goal clears all of them.** The plan was re-drafted; none of the
    old answers are about the new plan.
  * **a stale plan judges nothing**, per-phase included.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (chat, plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             verifier as vf, worker)


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
        self.sent = []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


TWO_PHASES = pl.Plan(
    goal="finish the export",
    phases=[pl.Phase(title="drain the queue",
                     verified_when="the queue length reads 0"),
            pl.Phase(title="re-run the export",
                     verified_when="export.csv has 1,204 rows")])


def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), TWO_PHASES)
    return tsk.start(config, agent, t)


def _pass(**kw):
    return {"state": "PASS", "why": "the console shows 0"}


def _fail(**kw):
    return {"state": "FAIL", "why": "the queue is still at 40"}


# ── the number exists ─────────────────────────────────────────────────

def test_a_new_task_is_on_the_first_phase(config, agent):
    assert tsk.earliest_incomplete(_task(config, agent)) == 0


def test_a_phase_is_complete_only_when_the_verifier_said_so(config, agent):
    t = _task(config, agent)
    t = ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    assert tsk.earliest_incomplete(tsk.get(config, agent, t.id)) == 1


def test_a_failed_phase_does_not_advance(config, agent):
    t = _task(config, agent)
    t = ses.verify(config, agent, t, verifier=_fail, evidence="…", phase=0)
    assert tsk.earliest_incomplete(tsk.get(config, agent, t.id)) == 0


def test_every_phase_passed_means_none_is_incomplete(config, agent):
    t = _task(config, agent)
    t = ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    t = ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=1)
    assert tsk.earliest_incomplete(tsk.get(config, agent, t.id)) is None


# ── judging one phase judges ONE criterion ────────────────────────────

def test_judging_a_phase_asks_only_about_that_phases_criterion(config, agent):
    """Otherwise 'phase 1 passed' means 'everything passed', and the number is
    decoration."""
    seen = {}

    def judge(**kw):
        seen.update(kw)
        return {"state": "PASS", "why": "ok"}

    ses.verify(config, agent, _task(config, agent), verifier=judge,
               evidence="…", phase=0)
    assert seen["criteria"] == ["the queue length reads 0"]


def test_the_phase_verdict_is_recorded_against_that_phase(config, agent):
    t = _task(config, agent)
    t = ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    got = tsk.phase_verdict(tsk.get(config, agent, t.id), 0)
    assert got["state"] == "PASS"
    assert tsk.phase_verdict(tsk.get(config, agent, t.id), 1) is None


def test_a_phase_out_of_range_is_refused(config, agent):
    with pytest.raises(IndexError):
        ses.verify(config, agent, _task(config, agent), verifier=_pass,
                   evidence="…", phase=7)


# ── a per-phase pass is not a task-level pass ─────────────────────────

def test_passing_one_phase_does_not_verify_the_task(config, agent):
    t = _task(config, agent)
    t = ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    assert tsk.get(config, agent, t.id).state != tsk.VERIFIED


def test_passing_every_phase_verifies_the_task(config, agent):
    t = _task(config, agent)
    t = ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    t = ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=1)
    assert tsk.get(config, agent, t.id).state == tsk.VERIFIED


def test_the_task_verdict_names_how_it_was_reached(config, agent):
    t = _task(config, agent)
    ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    t = ses.verify(config, agent, tsk.get(config, agent, t.id),
                   verifier=_pass, evidence="…", phase=1)
    assert "phase" in (t.verdict.get("why") or "").lower()


# ── the standard changing clears what it judged ───────────────────────

def test_editing_a_phases_criterion_clears_that_phases_verdict(config, agent):
    """It was judged against a standard that no longer exists."""
    t = _task(config, agent)
    ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    chat.handle(config, agent, f"/edit {t.id} 1 the console reports zero queued",
                surface="cli")
    after = tsk.get(config, agent, t.id)
    assert tsk.phase_verdict(after, 0) is None
    assert tsk.earliest_incomplete(after) == 0


def test_editing_one_phase_leaves_the_others_verdict_alone(config, agent):
    t = _task(config, agent)
    ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    chat.handle(config, agent, f"/edit {t.id} 2 export.csv has 1,300 rows",
                surface="cli")
    assert tsk.phase_verdict(tsk.get(config, agent, t.id), 0)["state"] == "PASS"


def test_moving_the_goal_clears_every_phase_verdict(config, agent):
    """The plan was re-drafted; none of the old answers are about it."""
    t = _task(config, agent)
    ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    chat.handle(config, agent, f"/goal {t.id} rebuild the search index",
                surface="cli")
    after = tsk.get(config, agent, t.id)
    assert tsk.phase_verdict(after, 0) is None


# ── a stale plan judges nothing, per-phase included ───────────────────

def test_a_stale_plan_refuses_a_phase_verdict_too(config, agent):
    t = _task(config, agent)
    t.plan_stale = True
    tsk._touch(agent, t, time.time)
    asked = []
    t = ses.verify(config, agent, tsk.get(config, agent, t.id),
                   verifier=lambda **kw: asked.append(kw) or _pass(),
                   evidence="…", phase=0)
    assert asked == []
    assert tsk.phase_verdict(tsk.get(config, agent, t.id), 0) is None


# ── what the session is told ──────────────────────────────────────────

def test_the_kickoff_points_at_the_real_earliest_incomplete_phase(config, agent):
    """The whole point: a plan whose first phase is done must not tell the
    session to start there."""
    t = _task(config, agent)
    ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    t = tsk.get(config, agent, t.id)
    text = ses.kickoff(t, tsk.read_plan(config, agent, t))
    # It must point at phase 2. Naming phase 1 as already-verified is fine and
    # useful — what must not happen is being SENT there.
    pointed = [ln for ln in text.splitlines()
               if ln.startswith("Earliest incomplete phase:")]
    assert pointed == ["Earliest incomplete phase: re-run the export"]
    assert "do not redo: drain the queue" in text


def test_the_kickoff_says_which_phases_are_already_done(config, agent):
    t = _task(config, agent)
    ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    t = tsk.get(config, agent, t.id)
    text = ses.kickoff(t, tsk.read_plan(config, agent, t)).lower()
    assert "verified" in text or "already" in text


# ── and what the owner is told ────────────────────────────────────────

def test_why_shows_each_phase_and_its_state(config, agent):
    from ai4science.harness.agents.sarsi import why as wy
    t = _task(config, agent)
    ses.verify(config, agent, t, verifier=_pass, evidence="…", phase=0)
    out = wy.explain(config, agent, tsk.get(config, agent, t.id))
    assert "drain the queue" in out and "re-run the export" in out
    assert "PASS" in out


def test_why_no_longer_says_progress_is_untracked(config, agent):
    """It is tracked now. Saying otherwise would be the opposite lie."""
    from ai4science.harness.agents.sarsi import why as wy
    out = wy.explain(config, agent, _task(config, agent)).lower()
    assert "not tracked" not in out


# ── the surfaces ──────────────────────────────────────────────────────

def test_the_supervision_loop_judges_the_phase_the_work_is_on(config, agent):
    """It judged all criteria at once, so a two-phase task could never pass its
    first phase — the evidence for phase 2 did not exist yet."""
    from ai4science.harness.agents.sarsi import operator as op

    t = _task(config, agent)
    t.plan_agreed = True
    rt = FakeRuntime()
    t = ses.assign(config, agent, t, runtime=rt)
    t.kickoff_pending = None          # briefed; the loop reaches the verifier
    t.state = tsk.RUNNING
    tsk._touch(agent, t, time.time)
    seen = []

    class Pane:
        def capture(self, name):
            return "the queue length reads 0\n❯ "

        def send(self, name, text):
            pass

        def key(self, name, key):
            pass

    def judge(**kw):
        seen.append(kw["criteria"])
        return {"state": "PASS", "why": "the console shows 0"}

    op.tick(config, agent, t, pane=Pane(), verifier=judge, engine="gpt")
    assert seen == [["the queue length reads 0"]]
