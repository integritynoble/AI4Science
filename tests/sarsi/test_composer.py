"""`S` — steer the plan's earliest incomplete phase.

The composer writes **one** instruction and types it. What it is given matters
more than what it says, so most of these tests are about the workspace it reads:

  * the approved plan text, and the phase it is driving — **named**, so the
    session knows where it is;
  * what the verifier last refused, so the next prompt addresses that;
  * what the **owner** said, on either surface — this was a real bug in the
    console: an instruction reached `clarify` and nothing else, so *"use the
    staging host"* never got in front of the node that writes the next prompt;
  * its own last few prompts, so it does not repeat what already failed;
  * any failure signature `EC` found, every round it persists.

And two refusals: a **stale** plan is withheld — improvising against the goal
beats marching through phases the owner has abandoned — and the composer may
never declare the work done. Only the verifier rules.
"""
import pytest

from ai4science.harness.agents.sarsi import (composer as cp, ownerlog, plan as pl,
                                             registry as reg, resultcheck as rc,
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


def _plan():
    return pl.Plan(goal="finish the export",
                   phases=[pl.Phase(title="drain the queue",
                                    verified_when="the queue length reads 0"),
                           pl.Phase(title="re-run the export",
                                    verified_when="export.csv has 1,204 rows")])


def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), _plan())
    t = tsk.start(config, agent, t)
    t.session = {"name": "work-abcd", "engine": "claude", "ceiling": "A1"}
    return t


def _model(reply="run the drain script"):
    def call(prompt):
        call.prompt = prompt
        return reply
    return call


# ── what it writes ────────────────────────────────────────────────────

def test_it_composes_one_instruction(config, agent):
    out = cp.compose(config, agent, _task(config, agent), screen="", model=_model())
    assert out.instruction == "run the drain script"


def test_it_names_the_phase_it_is_driving(config, agent):
    out = cp.compose(config, agent, _task(config, agent), screen="", model=_model())
    assert out.phase == "drain the queue"


def test_a_model_that_says_nothing_steers_nothing(config, agent):
    out = cp.compose(config, agent, _task(config, agent), screen="",
                     model=_model("   "))
    assert out.instruction is None


def test_the_composer_may_not_declare_the_work_done(config, agent):
    """Only the verifier rules. A model that answers DONE has not verified it."""
    out = cp.compose(config, agent, _task(config, agent), screen="",
                     model=_model("DONE"))
    assert out.instruction is None
    assert "verifier" in out.note.lower()


# ── what it is given ──────────────────────────────────────────────────

def test_the_plan_and_its_criteria_reach_the_prompt(config, agent):
    model = _model()
    cp.compose(config, agent, _task(config, agent), screen="", model=model)
    assert "the queue length reads 0" in model.prompt


def test_the_last_verdict_reaches_the_prompt(config, agent):
    t = _task(config, agent)
    t.verdict = {"state": "FAIL", "why": "only 3 rows"}
    model = _model()
    cp.compose(config, agent, t, screen="", model=model)
    assert "only 3 rows" in model.prompt


def test_what_the_owner_said_reaches_the_prompt(config, agent):
    """The real console bug: an instruction reached `clarify` and nothing else,
    so the composer could steer straight against the owner."""
    ownerlog.append(config, agent, "use the staging host, not production",
                    surface="telegram")
    model = _model()
    cp.compose(config, agent, _task(config, agent), screen="", model=model)
    assert "staging host" in model.prompt


def test_its_own_recent_prompts_reach_the_prompt(config, agent):
    t = _task(config, agent)
    cp.remember(config, agent, t, "run the drain script")
    model = _model()
    cp.compose(config, agent, t, screen="", model=model)
    assert "run the drain script" in model.prompt
    assert "do not repeat" in model.prompt.lower()


def test_a_failure_signature_reaches_the_prompt_every_round(config, agent):
    screen = "Traceback (most recent call last):\nValueError: no such column\n"
    model = _model()
    cp.compose(config, agent, _task(config, agent), screen=screen, model=model)
    assert "traceback" in model.prompt.lower()


def test_a_clean_screen_adds_no_reassurance(config, agent):
    model = _model()
    cp.compose(config, agent, _task(config, agent), screen="all good\n❯\n",
               model=model)
    assert "no problems" not in model.prompt.lower()


# ── the stale plan ────────────────────────────────────────────────────

def test_a_stale_plan_is_withheld_and_the_goal_stands(config, agent):
    t = _task(config, agent)
    t.plan_stale = True
    t.criteria = []
    model = _model()
    out = cp.compose(config, agent, t, screen="", model=model)
    assert "the queue length reads 0" not in model.prompt
    assert "finish the export" in model.prompt          # improvise against the goal
    assert out.phase is None


def test_a_stale_plan_says_why_it_is_improvising(config, agent):
    t = _task(config, agent)
    t.plan_stale = True
    model = _model()
    cp.compose(config, agent, t, screen="", model=model)
    assert "stale" in model.prompt.lower()


# ── remembering, so it does not loop ──────────────────────────────────

def test_remembering_is_bounded(config, agent):
    t = _task(config, agent)
    for i in range(12):
        cp.remember(config, agent, t, f"attempt {i}")
    assert len(cp.recent(config, agent, t)) <= cp.KEEP_PROMPTS


def test_the_most_recent_prompts_are_the_ones_kept(config, agent):
    t = _task(config, agent)
    for i in range(12):
        cp.remember(config, agent, t, f"attempt {i}")
    assert "attempt 11" in cp.recent(config, agent, t)


def test_prompts_are_remembered_per_task(config, agent):
    a, b = _task(config, agent), _task(config, agent)
    cp.remember(config, agent, a, "only mine")
    assert cp.recent(config, agent, b) == []


# ── steering types it ─────────────────────────────────────────────────

def test_steer_types_the_instruction_and_remembers_it(config, agent):
    sent = []

    class Pane:
        def send(self, name, text):
            sent.append(text)

    t = _task(config, agent)
    out = cp.steer(config, agent, t, screen="", model=_model(), pane=Pane())
    assert sent == ["run the drain script"]
    assert "run the drain script" in cp.recent(config, agent, t)
    assert out.instruction == "run the drain script"


def test_steer_types_nothing_when_there_is_nothing_to_say(config, agent):
    sent = []

    class Pane:
        def send(self, name, text):
            sent.append(text)

    cp.steer(config, agent, _task(config, agent), screen="",
             model=_model("DONE"), pane=Pane())
    assert sent == []
