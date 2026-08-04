"""`why` — "why are you doing this?", answered from what is recorded.

Three things the system already knows and never showed together: the goal, the
criteria a verdict will be judged against, and what the last verdict actually
said. Assembling them took three commands and the owner's memory.

The hard rule here is that `why` **reports and never infers**. It is the command
you reach for when you distrust the others, so a plausible-sounding answer is
worse than a short one:

  * **the phase it names comes from the verdicts, never a guess.** A phase is
    done when a verdict says so *about that phase*; with none it reads "not
    judged yet". (Writing this command is what exposed that the number did not
    exist at all — see `test_phases.py`.)
  * **"not judged yet" is not "in progress".** A task with no verdict says so.
  * **a stale plan says its criteria are not the standard any more**, because
    that is the one case where the listed criteria will not be applied.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             verifier as vf, why as wy, worker)


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

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None,
              writable=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


PLAN = pl.Plan(goal="finish the export",
               phases=[pl.Phase(title="drain the queue",
                                verified_when="the queue length reads 0"),
                       pl.Phase(title="re-run the export",
                                verified_when="export.csv has 1,204 rows")])


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), PLAN)
    return tsk.start(config, agent, t)


# ── the three things, together ────────────────────────────────────────

def test_it_states_the_goal(config, agent):
    out = wy.explain(config, agent, _task(config, agent))
    assert "finish the export" in out


def test_it_lists_the_criteria_a_verdict_will_apply(config, agent):
    out = wy.explain(config, agent, _task(config, agent))
    assert "the queue length reads 0" in out
    assert "export.csv has 1,204 rows" in out


def test_it_gives_the_last_verdicts_reason(config, agent):
    t = _task(config, agent)
    t.verdict = vf.parse("FAIL: export.csv has 0 rows, not 1204")
    tsk._touch(agent, t, __import__("time").time)
    out = wy.explain(config, agent, tsk.get(config, agent, t.id))
    assert "FAIL" in out and "export.csv has 0 rows" in out


# ── it reports, it does not infer ─────────────────────────────────────

def test_an_unjudged_phase_is_never_shown_as_done(config, agent):
    """Progress is tracked now — but only by verdicts. A phase nobody judged
    reads "not judged yet", because silence is not success."""
    out = wy.explain(config, agent, _task(config, agent)).lower()
    assert out.count("not judged yet") >= 2          # both phases
    assert "pass" not in out


def test_no_verdict_says_not_judged_rather_than_in_progress(config, agent):
    out = wy.explain(config, agent, _task(config, agent))
    assert "not been judged" in out.lower() or "not judged" in out.lower()
    assert "in progress" not in out.lower()


def test_a_stale_plan_says_its_criteria_are_not_the_standard(config, agent):
    """The one case where the criteria it just listed will not be applied."""
    t = _task(config, agent)
    t.plan_stale = True
    tsk._touch(agent, t, __import__("time").time)
    out = wy.explain(config, agent, tsk.get(config, agent, t.id)).lower()
    assert "stale" in out


def test_a_task_with_no_plan_says_so_rather_than_showing_nothing(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="a bare goal")
    t = tsk.create(config, agent, d)
    out = wy.explain(config, agent, t)
    assert "no plan" in out.lower()
    assert "a bare goal" in out


# ── the rest of the context the owner needs ───────────────────────────

def test_it_says_what_the_task_waits_on(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="read my mail",
                         requires_secrets=["mail.read"])
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    assert "mail.read" in wy.explain(config, agent, t)


def test_it_says_who_is_driving(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t.steering_paused = True
    tsk._touch(agent, t, __import__("time").time)
    out = wy.explain(config, agent, tsk.get(config, agent, t.id)).lower()
    assert "you" in out and "wheel" in out


def test_it_counts_the_retries_it_has_spent(config, agent):
    t = _task(config, agent)
    t.retries = 2
    t.verdict = vf.parse("FAIL: still empty")
    tsk._touch(agent, t, __import__("time").time)
    assert "2" in wy.explain(config, agent, tsk.get(config, agent, t.id))


def test_it_names_the_session_so_the_answer_can_be_checked(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert t.session["name"] in wy.explain(config, agent, t)


# ── the chat door ─────────────────────────────────────────────────────

def test_slash_why_answers_about_a_named_task(config, agent):
    from ai4science.harness.agents.sarsi import chat
    t = _task(config, agent)
    out = chat.handle(config, agent, f"/why {t.id}", surface="cli")
    assert "the queue length reads 0" in out


def test_bare_why_answers_about_the_task_you_are_standing_in(config, agent):
    """You are already in it — naming it again is the friction the cursor
    exists to remove."""
    from ai4science.harness.agents.sarsi import chat
    t = _task(config, agent)
    chat.handle(config, agent, f"/{t.id}", surface="cli")       # stand in it
    out = chat.handle(config, agent, "why", surface="cli")
    assert "the queue length reads 0" in out


def test_bare_why_with_no_cursor_says_which_task_it_needs(config, agent):
    from ai4science.harness.agents.sarsi import chat
    _task(config, agent)
    out = chat.handle(config, agent, "why", surface="cli")
    assert "which task" in out.lower() or "/why <task>" in out
