"""A criterion must be checkable from what the verifier is actually given.

Live on grace, a session planned this:

    Verified when: the transcript contains a Read of `.../scores.csv` returning
    all 4 lines, and the stated answer is exactly `id=b, score=11`

and the run closed UNVERIFIED with *"the visible evidence contains no Read tool
call … the only support is the session's own narration, which is not evidence"*.
The work was right — `top.md` said `b`/`11`, which is the correct answer — and it
could not be judged, because **the verifier has no transcript**.

`evidence.gather` gives it two things: the files under the task's evidence roots,
and the pane, appended under the heading *"WHAT THE SESSION SAID (narration — not
evidence; a claim on a screen is not the thing it claims)"*. The session's
tool-call log is not among them and never has been. So a criterion about the
transcript is unmeetable by construction — not hard to meet, impossible.

The brief already said *"name what an independent verifier must SEE — a file, a
count, an exit code — never an intention"*, and that is why this got through: the
transcript containing a Read **is** a concrete observable, and it **is not** an
intention. The rule ruled out the wrong thing. What it has to say is not *be
concrete* but *be checkable from the artefacts*, because artefacts are all the
verifier gets.

The session's own recovery is the tell. Handed the FAIL, it rewrote the line to
`A verifier recomputes this from the file itself — no transcript needed` — it
could see the rule once the failure spelled it out. The brief should have said it
first.
"""
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


@pytest.fixture
def brief(config, agent):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return ses.planning_kickoff(config, agent, t)


# ── it says what the verifier is given ────────────────────────────────

def test_the_brief_says_the_verifier_reads_the_files(brief):
    low = brief.lower()
    assert "file" in low
    assert "verifier" in low


def test_and_that_it_has_no_transcript(brief):
    """The specific thing the live session assumed it had."""
    assert "transcript" in brief.lower()


def test_and_that_narration_is_not_evidence(brief):
    """The pane IS handed over — under a heading saying it does not count. A
    session told only "the verifier has no transcript" could reasonably plan
    around what it says on screen instead."""
    low = brief.lower()
    assert "narration" in low or "what you say" in low or "said" in low


def test_it_gives_the_shape_of_a_criterion_that_works(brief):
    """A rule with no example is a rule an author has to guess at."""
    assert "Verified when:" in brief


# ── and it still says the old things ──────────────────────────────────

def test_intentions_are_still_ruled_out(brief):
    """The previous rule was not wrong, it was incomplete. Both hold."""
    assert "intention" in brief.lower()


def test_the_session_is_still_told_to_stop(brief):
    """A session that plans and then works has done work nobody granted."""
    assert "stop" in brief.lower()


def test_the_plan_file_is_still_named(brief):
    assert "plan0.md" in brief or "plan at" in brief


# ── the rule is one a criterion can be checked against ────────────────

@pytest.mark.parametrize("bad", [
    "the transcript contains a Read of scores.csv returning all 4 lines",
    "the session's tool calls show a Write to top.md",
    "my narration states the id and the score",
])
def test_the_brief_rules_out_the_shapes_that_cannot_be_judged(brief, bad):
    """Each of these names something real that the verifier cannot see. The
    brief has to make that distinction explicit enough for an author to apply
    it, so it names the sources rather than only the failure."""
    low = brief.lower()
    assert "transcript" in low and ("tool call" in low or "tool-call" in low
                                    or "narration" in low)


# ── and the correction says the same thing ────────────────────────────

def test_the_replan_nudge_carries_the_same_rule(config, agent):
    """A session whose plan will not parse is sent back to fix it. Telling it
    only "name what an independent verifier must see" is the wording that let
    the transcript criterion through in the first place — a session corrected
    twice with the incomplete rule learns the incomplete rule."""
    import time

    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t = ses.assign(config, agent, t, runtime=_Runtime(), installed=lambda: set())

    # a plan with a phase and no `Verified when:` line at all
    (tsk.dir_of(agent, t.id) / ses.PLAN_FILE).write_text(
        "# goal\n\n## Phase 1 — do it\nSome steps.\n")

    rt = _Runtime()
    ses.collect_plan(config, agent, t, runtime=rt, session_idle=True,
                     now=time.time)
    said = " ".join(rt.sent).lower()
    assert said, "the session was never told its plan could not be used"
    assert "transcript" in said
    assert "file" in said


class _Runtime:
    engine = "claude"

    def __init__(self):
        self.sent = []

    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text, **kw):
        self.sent.append(text)
        return {"ok": True}

    def stop(self, name):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        """Part of the runtime contract — a double omitting it was hidden by a
        swallowed exception in `release` until that stopped being swallowed."""
        return {"name": name, "ceiling": ceiling}
