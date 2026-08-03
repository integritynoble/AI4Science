"""The board, on whichever door the owner came through.

`/tasks` lists them, `/<task>` opens one, and opening one is also the way into
its `sarsi-claude` session — Guided, Interact, History.

Interact **does not relay**. It pauses the worker's steering, marks the plan
stale, and hands over the terminal. A relay would leave two things typing into
one pane with a protocol deciding who wins.
"""
import pytest

from ai4science.harness.agents.sarsi import (chat, plan as pl, registry as reg,
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
    def __init__(self):
        self.started, self.sent = [], []

    def start(self, name, cwd, *, govern, ceiling, env=None):
        self.started.append(name)
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append((name, text))
        return {"ok": True}


def _plan():
    return pl.Plan(goal="finish the export",
                   phases=[pl.Phase(title="drain the queue",
                                    verified_when="the queue length reads 0"),
                           pl.Phase(title="re-run the export",
                                    verified_when="export.csv has 1,204 rows")])


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), _plan())
    return tsk.start(config, agent, t)


def _say(config, agent, text, surface="telegram", runtime=None):
    return chat.handle(config, agent, text, surface=surface,
                       runtime=runtime or FakeRuntime())


# ── /tasks, on either door ────────────────────────────────────────────

def test_tasks_lists_every_task_with_its_state(config, agent):
    _task(config, agent, "finish the export")
    out = _say(config, agent, "/tasks")
    assert "finish the export" in out and "running" in out


def test_tasks_says_the_same_thing_on_both_surfaces(config, agent):
    """A surface is a door, not a scope."""
    _task(config, agent)
    assert _say(config, agent, "/tasks", surface="cli") == \
        _say(config, agent, "/tasks", surface="telegram")


def test_tasks_with_none_says_so_rather_than_answering_emptily(config, agent):
    assert "no tasks" in _say(config, agent, "/tasks").lower()


def test_a_task_waiting_on_a_grant_says_what_it_waits_for(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="read my mail",
                         requires_secrets=["mail.read"])
    tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    assert "mail.read" in _say(config, agent, "/tasks")


# ── /<task> opens one ─────────────────────────────────────────────────

def test_opening_a_task_shows_its_plan_and_criteria(config, agent):
    t = _task(config, agent)
    out = _say(config, agent, f"/{t.id}")
    assert "the queue length reads 0" in out


def test_a_task_can_be_opened_by_a_unique_prefix(config, agent):
    t = _task(config, agent)
    assert t.id in _say(config, agent, f"/{t.id[:8]}")


def test_an_unknown_task_says_so_and_does_not_guess(config, agent):
    out = _say(config, agent, "/tsk_nothing")
    assert "no task" in out.lower()


def test_an_ambiguous_prefix_refuses_rather_than_picking_one(config, agent):
    """Guessing which task the owner meant is how the wrong session gets
    stopped."""
    _task(config, agent, "job one")
    _task(config, agent, "job two")
    out = _say(config, agent, "/tsk_")
    assert "which" in out.lower() or "ambiguous" in out.lower()


def test_opening_a_task_offers_the_three_modes(config, agent):
    t = _task(config, agent)
    out = _say(config, agent, f"/{t.id}").lower()
    assert "guided" in out and "interact" in out and "history" in out


# ── Guided: the worker steers ─────────────────────────────────────────

def test_guided_sends_the_instruction_through_the_worker(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/guided {t.id} add tests first", runtime=rt)
    assert "add tests first" in rt.sent[-1][1]


def test_guided_on_a_task_with_no_session_says_so(config, agent):
    t = _task(config, agent)
    out = _say(config, agent, f"/guided {t.id} do the thing")
    assert "no session" in out.lower()


# ── Interact: it opens the door and stands back ───────────────────────

def test_interact_hands_over_the_tmux_line_rather_than_relaying(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    out = _say(config, agent, f"/interact {t.id}", runtime=rt)
    assert f"tmux attach -t {t.session['name']}" in out
    assert rt.sent[1:] == []          # nothing relayed; only the kickoff was sent


def test_interact_pauses_the_workers_steering(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/interact {t.id}", runtime=rt)
    assert tsk.get(config, agent, t.id).steering_paused is True


def test_interact_makes_the_plan_stale(config, agent):
    """So steering does not resume by marching through phases the owner has
    just abandoned by hand."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/interact {t.id}", runtime=rt)
    assert tsk.get(config, agent, t.id).plan_stale is True


def test_a_paused_task_is_not_steered_by_guided(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/interact {t.id}", runtime=rt)
    out = _say(config, agent, f"/guided {t.id} keep going", runtime=rt)
    assert "keep going" not in "".join(text for _, text in rt.sent)
    assert "resume" in out.lower()


def test_resume_gives_the_wheel_back_to_the_worker(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    _say(config, agent, f"/interact {t.id}", runtime=rt)
    _say(config, agent, f"/resume {t.id}", runtime=rt)
    _say(config, agent, f"/guided {t.id} keep going", runtime=rt)
    assert "keep going" in rt.sent[-1][1]


# ── the owner edits the plan ──────────────────────────────────────────

def test_edit_changes_the_criterion_the_verifier_will_apply(config, agent):
    t = _task(config, agent)
    _say(config, agent, f"/edit {t.id} 1 the queue is empty in the console")
    assert tsk.get(config, agent, t.id).criteria[0] == \
        "the queue is empty in the console"


def test_an_owner_edit_makes_the_plan_fresh_and_owned(config, agent):
    t = _task(config, agent)
    rt = FakeRuntime()
    _say(config, agent, f"/interact {t.id}", runtime=rt)      # marks it stale
    _say(config, agent, f"/edit {t.id} 1 the queue is empty")
    after = tsk.get(config, agent, t.id)
    assert after.plan_stale is False and after.plan_owner_edited is True


def test_editing_a_phase_that_does_not_exist_says_so(config, agent):
    t = _task(config, agent)
    assert "phase" in _say(config, agent, f"/edit {t.id} 9 whatever").lower()


def test_an_owner_edited_plan_survives_the_next_polish_as_a_proposal(config, agent):
    t = _task(config, agent)
    _say(config, agent, f"/edit {t.id} 1 mine, not yours")
    plan = tsk.read_plan(config, agent, tsk.get(config, agent, t.id))
    outcome = plan.polish(phases=[pl.Phase(title="agent's idea",
                                           verified_when="whatever it prefers")])
    assert outcome.adopted is False
    assert outcome.plan.criteria()[0] == "mine, not yours"


# ── anything that is not a command ────────────────────────────────────

def test_plain_text_is_not_swallowed_as_a_command(config, agent):
    out = _say(config, agent, "how are the exports going?")
    assert "how are the exports going?" in out


def test_an_unknown_slash_command_lists_the_real_ones(config, agent):
    out = _say(config, agent, "/frobnicate")
    assert "/tasks" in out
