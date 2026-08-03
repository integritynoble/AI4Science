"""Answering the session's questions — instead of waking the owner for each one.

Claude Code asks things. *"Which directory should I put this in?"* *"Do you want
tests first?"* *"Which of these two approaches?"* Before this, every one of them
stopped the loop and waited for a person, which makes an unattended agent a
thing that pages you every few minutes.

An agent may answer — but only from **what it already holds**: the goal, the
plan and its criteria, the scope of the directive, and what the owner has
actually said. That is the whole rule, and everything below is it:

  * **an answer must be derivable.** If the workspace does not settle it, the
    agent escalates and quotes the question. Guessing on the owner's behalf and
    guessing *as* the owner are the same act.
  * **owner facts are never answered.** A salary expectation, a start date, a
    reference's details — the agent asks rather than invents, and a question is
    not a licence to invent.
  * **authority is never answered here.** A permission prompt goes to the gate
    allowlist; a request for a secret goes to the vault. A question that would
    widen what the session may do is not a clarification.
  * **what it decided is recorded.** Answering on someone's behalf is delegation,
    and delegation nobody can see is indistinguishable from an agent doing as it
    pleases.
"""
import pytest

from ai4science.harness.agents.sarsi import (answering as ans, ownerlog,
                                             plan as pl, registry as reg,
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


def _task(config, agent, goal="finish the export", criteria=("export.csv has 1,204 rows",)):
    d = worker.Directive(agent_id=agent.id, goal=goal, scope=["/home/me/reports"])
    p = pl.Plan(goal=goal, phases=[pl.Phase(title="do it", verified_when=c)
                                   for c in criteria])
    return tsk.start(config, agent, tsk.attach_plan(config, agent,
                                                    tsk.create(config, agent, d), p))


def _model(reply):
    def call(prompt):
        call.prompt = prompt
        return reply
    return call


# ── is the session even asking? ───────────────────────────────────────

def test_a_plain_working_screen_is_not_a_question(config, agent):
    assert ans.question_on(" writing files…\n❯\n") is None


def test_a_direct_question_is_detected(config, agent):
    q = ans.question_on("Which directory should I write the export to?\n❯\n")
    assert q and "directory" in q


def test_a_permission_prompt_is_not_a_question_for_this_node(config, agent):
    """That is the gate's business, and its allowlist. Answering it here would
    route around the one place authority is decided."""
    assert ans.question_on("Do you want to proceed?\n ❯ 1. Yes\n   2. No\n") is None


# ── answering from what it holds ──────────────────────────────────────

def test_it_answers_from_the_plan(config, agent):
    t = _task(config, agent)
    out = ans.answer(config, agent, t,
                     question="How many rows should the export have?",
                     model=_model("1,204 rows, per the plan's criterion."))
    assert out.answer and "1,204" in out.answer


def test_the_prompt_carries_the_goal_the_criteria_and_the_scope(config, agent):
    t = _task(config, agent)
    model = _model("…")
    ans.answer(config, agent, t, question="Where do I write it?", model=model)
    assert "finish the export" in model.prompt
    assert "export.csv has 1,204 rows" in model.prompt
    assert "/home/me/reports" in model.prompt


def test_what_the_owner_said_is_available_to_answer_from(config, agent):
    ownerlog.append(config, agent, "use the staging host, not production",
                    surface="cli")
    t = _task(config, agent)
    model = _model("The staging host.")
    ans.answer(config, agent, t, question="Which host?", model=model)
    assert "staging host" in model.prompt


# ── when it cannot be derived ─────────────────────────────────────────

def test_an_underivable_question_escalates_and_quotes_it(config, agent):
    t = _task(config, agent)
    out = ans.answer(config, agent, t, question="Should I use Postgres or MySQL?",
                     model=_model("ASK-THE-OWNER"))
    assert out.answer is None
    assert "Postgres or MySQL" in out.escalate


def test_the_model_is_told_to_refuse_rather_than_guess(config, agent):
    t = _task(config, agent)
    model = _model("ASK-THE-OWNER")
    ans.answer(config, agent, t, question="q", model=model)
    assert "ASK-THE-OWNER" in model.prompt
    assert "do not guess" in model.prompt.lower()


def test_a_model_that_errors_escalates_rather_than_inventing(config, agent):
    def boom(prompt):
        raise RuntimeError("no engine")

    t = _task(config, agent)
    out = ans.answer(config, agent, t, question="q", model=boom)
    assert out.answer is None and "no engine" in out.escalate


# ── what it must never answer ─────────────────────────────────────────

@pytest.mark.parametrize("question", [
    "What salary expectation should I put on the form?",
    "What is your start date?",
    "Can you give me a reference's contact details?",
])
def test_an_owner_fact_is_never_answered(config, question):
    c = config
    jobs = c.agents["jobs"]
    t = _task(c, jobs)
    out = ans.answer(c, jobs, t, question=question, model=_model("£70,000"))
    assert out.answer is None
    assert "owner" in out.escalate.lower()


def test_a_request_for_a_secret_is_never_answered(config, agent):
    t = _task(config, agent)
    out = ans.answer(config, agent, t,
                     question="What is the SMTP password for the mail account?",
                     model=_model("hunter2"))
    assert out.answer is None
    assert "vault" in out.escalate.lower()


def test_a_request_to_widen_authority_is_never_answered(config, agent):
    t = _task(config, agent)
    out = ans.answer(config, agent, t,
                     question="Shall I run this with sudo to get past the error?",
                     model=_model("yes, go ahead"))
    assert out.answer is None


# ── it is recorded ────────────────────────────────────────────────────

def test_an_answer_is_recorded_with_the_question(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    t = _task(config, agent)
    ans.answer(config, agent, t, question="How many rows?",
               model=_model("1,204."))
    row = ledger.read(config, "reports")[-1]
    assert row["state"] == "answered-question"
    assert "How many rows?" in row["evidence"][0]


def test_an_escalation_is_recorded_too(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    t = _task(config, agent)
    ans.answer(config, agent, t, question="Postgres or MySQL?",
               model=_model("ASK-THE-OWNER"))
    assert ledger.count(config, "reports", state="question") == 1
