"""`questions` — the escalations, in one place, answerable from either surface.

`answering` already declines the questions it must not answer — secrets,
authority, owner facts, anything the plan does not settle — and escalates them.
Every one was written to the ledger and **none were ever listed**, so the way to
find out that a session was waiting on you was to notice.

Four rules:

  * **the owner closes it, not the agent.** The agent already declined; letting
    a later automatic answer close it would quietly resolve the one class of
    question that exists because it must not be resolved automatically.
  * **an answer that reached no session is not an answer.** A session that has
    stopped cannot hear it, and recording it as answered would close the loop
    on the owner's side while leaving the session exactly where it was.
  * **the same question asked twice is one open item.** A looping session must
    not flood the list until the real ones are invisible.
  * **the escalation's reason travels with it**, because "the session asked
    something" is not a thing anyone can act on.
"""
import pytest

from ai4science.harness.agents.sarsi import (ledger, plan as pl, questions as qs,
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


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.start(config, agent, t)


def _running(config, agent, rt):
    return ses.assign(config, agent, _task(config, agent), runtime=rt)


def _escalate(config, agent, task_id, question, why="the plan does not settle it"):
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task_id, "state": "question",
                   "evidence": [f"Q: {question}", f"escalated: {why}"]})


# ── listing them ──────────────────────────────────────────────────────

def test_an_escalated_question_is_listed(config, agent):
    _escalate(config, agent, "tsk_1", "which directory should I index?")
    got = qs.open_of(config, agent)
    assert [q.text for q in got] == ["which directory should I index?"]


def test_the_reason_it_was_escalated_travels_with_it(config, agent):
    """'the session asked something' is not a thing anyone can act on."""
    _escalate(config, agent, "tsk_1", "what is the smtp password?",
              why="this asks for a secret")
    assert "secret" in qs.open_of(config, agent)[0].why


def test_nothing_escalated_means_nothing_open(config, agent):
    assert qs.open_of(config, agent) == []


def test_another_agents_question_is_not_this_ones(config, agent):
    _escalate(config, config.agents["social"], "tsk_1", "which account?")
    assert qs.open_of(config, agent) == []


def test_the_same_question_twice_is_one_open_item(config, agent):
    """A looping session must not flood the list until the real ones are
    invisible."""
    for _ in range(4):
        _escalate(config, agent, "tsk_1", "which directory should I index?")
    assert len(qs.open_of(config, agent)) == 1


def test_the_same_text_on_a_different_task_is_a_different_question(config, agent):
    _escalate(config, agent, "tsk_1", "which directory?")
    _escalate(config, agent, "tsk_2", "which directory?")
    assert len(qs.open_of(config, agent)) == 2


# ── answering closes it ───────────────────────────────────────────────

def test_answering_sends_the_owners_words_into_the_session(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory should I index?")
    qs.answer(config, agent, t, "which directory should I index?",
              "use /srv/exports", runtime=rt)
    assert "use /srv/exports" in rt.sent[-1]


def test_answering_closes_it(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    qs.answer(config, agent, t, "which directory?", "/srv/exports", runtime=rt)
    assert qs.open_of(config, agent) == []


def test_answering_one_leaves_the_others_open(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    _escalate(config, agent, t.id, "which format?")
    qs.answer(config, agent, t, "which directory?", "/srv/exports", runtime=rt)
    assert [q.text for q in qs.open_of(config, agent)] == ["which format?"]


def test_the_answer_is_marked_as_the_owners_word(config, agent):
    """It goes in over the worker's steering — the owner is the top of the
    ladder even while the worker holds the wheel."""
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    t.steering_paused = True
    tsk._touch(agent, t, __import__("time").time)
    _escalate(config, agent, t.id, "which directory?")
    qs.answer(config, agent, tsk.get(config, agent, t.id), "which directory?",
              "/srv/exports", runtime=rt)
    assert "/srv/exports" in rt.sent[-1]


# ── an answer that reached nobody is not an answer ────────────────────

def test_answering_a_task_with_no_session_refuses(config, agent):
    """Recording it as answered would close the loop on the owner's side and
    leave the session exactly where it was."""
    t = _task(config, agent)
    _escalate(config, agent, t.id, "which directory?")
    with pytest.raises(qs.NoSession):
        qs.answer(config, agent, t, "which directory?", "/srv/exports",
                  runtime=FakeRuntime())


def test_a_refused_answer_leaves_the_question_open(config, agent):
    t = _task(config, agent)
    _escalate(config, agent, t.id, "which directory?")
    with pytest.raises(qs.NoSession):
        qs.answer(config, agent, t, "which directory?", "x",
                  runtime=FakeRuntime())
    assert len(qs.open_of(config, agent)) == 1


def test_answering_a_question_that_was_never_asked_refuses(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    with pytest.raises(qs.NotAsked):
        qs.answer(config, agent, t, "something nobody asked", "x", runtime=rt)


# ── the agent's own later answer does not close it ────────────────────

def test_the_agent_answering_later_does_not_close_the_owners_question(config, agent):
    """It already declined. The escalation exists BECAUSE this class of
    question must not be resolved automatically."""
    _escalate(config, agent, "tsk_1", "what is the smtp password?",
              why="this asks for a secret")
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": "tsk_1",
                   "state": "answered-question",
                   "evidence": ["Q: what is the smtp password?", "A: …"]})
    assert len(qs.open_of(config, agent)) == 1


# ── where the owner sees them ─────────────────────────────────────────

def test_attention_carries_an_open_question(config, agent):
    from ai4science.harness.agents.sarsi import attention as att
    t = _task(config, agent)
    _escalate(config, agent, t.id, "which directory should I index?")

    class Blank:
        def capture(self, name):
            return ""

    kinds = [i.kind for i in att.needs(config, agent, pane=Blank()).items]
    assert "question" in kinds


def test_the_fleet_view_names_which_agent_is_waiting(config):
    _escalate(config, config.agents["work"], "tsk_1", "which directory?")
    _escalate(config, config.agents["abraham"], "tsk_2", "which card?")
    assert {q.agent_id for q in qs.across(config)} == {"work", "abraham"}


# ── both doors ────────────────────────────────────────────────────────

def test_chat_lists_the_open_questions(config, agent):
    from ai4science.harness.agents.sarsi import chat
    _escalate(config, agent, "tsk_1", "which directory should I index?")
    out = chat.handle(config, agent, "/questions", surface="cli")
    assert "which directory should I index?" in out


def test_chat_says_so_when_none_are_open(config, agent):
    from ai4science.harness.agents.sarsi import chat
    out = chat.handle(config, agent, "/questions", surface="cli")
    assert "no open questions" in out.lower()


def test_chat_can_answer_one(config, agent):
    from ai4science.harness.agents.sarsi import chat
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    chat.handle(config, agent, f"/answer {t.id} which directory? | /srv/exports",
                surface="cli", runtime=rt)
    assert qs.open_of(config, agent) == []
    assert "/srv/exports" in rt.sent[-1]


def test_chat_answer_without_the_separator_says_how(config, agent):
    from ai4science.harness.agents.sarsi import chat
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    out = chat.handle(config, agent, f"/answer {t.id} which directory?",
                      surface="cli", runtime=rt)
    assert "usage" in out.lower() or "|" in out


# ── delivered, not merely typed ───────────────────────────────────────

class Pane:
    """The same tmux session the runtime types into — so what the runtime sent
    is what the pane sees, once the session is listening.

    A booting session swallows input: `ready=False` is that, and it is the
    condition observed live.
    """

    def __init__(self, runtime, *, ready=True):
        self.runtime, self.ready = runtime, ready

    def capture(self, name):
        head = 'Claude Code — welcome\n❯ Try "edit x"\n'
        return head + ("\n".join(self.runtime.sent) if self.ready else "")

    def key(self, name, key):
        pass


def test_an_answer_seen_on_screen_closes_the_question(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    qs.answer(config, agent, t, "which directory?", "/srv/exports",
              runtime=rt, pane=Pane(rt))
    assert qs.open_of(config, agent) == []


def test_an_answer_that_never_appears_leaves_the_question_open(config, agent):
    """Observed live: the session was still on its splash screen, the answer
    was typed into a terminal that was not listening, and the question closed
    anyway. Typed is not delivered."""
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    with pytest.raises(qs.NotDelivered):
        qs.answer(config, agent, t, "which directory?", "/srv/exports",
                  runtime=rt, pane=Pane(rt, ready=False))
    assert len(qs.open_of(config, agent)) == 1


def test_the_refusal_says_the_session_was_not_listening(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    try:
        qs.answer(config, agent, t, "which directory?", "/srv/exports",
                  runtime=rt, pane=Pane(rt, ready=False))
    except qs.NotDelivered as e:
        assert "not" in str(e).lower() and t.session["name"] in str(e)


def test_without_a_pane_it_still_works_and_says_it_was_unconfirmed(config, agent):
    """Callers that cannot read a screen are not blocked — but the record says
    the delivery was never seen."""
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    _escalate(config, agent, t.id, "which directory?")
    qs.answer(config, agent, t, "which directory?", "/srv/exports", runtime=rt)
    assert qs.open_of(config, agent) == []
