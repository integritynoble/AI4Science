"""The plan you read and the criteria you are judged against, kept the same one.

`sarsi plan` renders `plan0.md`. `why` and `check` used `task.criteria`, a copy
taken when the plan was attached. Nothing kept them equal, so editing the plan
file — the obvious way to sharpen a criterion — silently produced two plans:

    $ sarsi plan social tsk_…      # shows the sharpened criterion
    Verified when: three files exist in ~/live-social named post1.md …

    $ sarsi check social tsk_…     # judged the ORIGINAL, provisional one
    FAIL: the evidence is only a directory listing …

Observed live on grace; it cost two FAILs and a retry. Worse than the wasted
run, the FAIL was *unarguable* on the criterion actually used, so nothing about
it looked like a bug: the verifier gathers the files a criterion names, the
stale criterion named none, and the reason it gave was true.

**The obvious fix is wrong.** "The file wins" was the first thing written here,
and the plan file lives in the task folder — which is the session's working
directory, and the kickoff tells it so: *"Your plan is plan0.md in this
folder."* Making the file authoritative at judging time lets the agent being
judged rewrite the standard it is judged against, and clear the verdicts that
already failed it. That is a worse defect than the one it fixes, and it would
have looked like a feature.

So the divergence is **detected and refused**, never silently adopted — the
propose/hold/sign shape this system already uses everywhere an agent-writable
thing must not authorise itself:

  * **drift is detected, and nothing is taken from the file on its own.**
  * **judging stops.** Not a FAIL — an `UNVERIFIED`, because which of the two
    criteria is meant is genuinely unknown, and a verdict either way would
    answer a question nobody has settled.
  * **only the owner adopts.** `sarsi adopt` takes the file as the standard,
    and a changed criterion clears that phase's verdict — `/edit`'s rule, since
    the phase was judged against a standard that no longer exists.
  * **only the phases that changed.** Adopting must not wipe verdicts that are
    still about the criterion which earned them.
  * **a stale plan is exempt.** It is stale precisely because it no longer
    describes what happened, and `_interact` withholds its criteria on purpose.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
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


def _task(config, agent, goal="draft three posts"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    return tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                           pl.draft(d))


def _plan_path(agent, t):
    return tsk.dir_of(agent, t.id) / f"{t.plan_version}.md"


def _rewrite(agent, t, *criteria):
    body = [f"# {t.goal}", ""]
    for i, c in enumerate(criteria, 1):
        body += [f"## Phase {i} — do the work", f"Verified when: {c}", ""]
    _plan_path(agent, t).write_text("\n".join(body))


SHARP = ("three files exist in /tmp/live-social named post1.md, post2.md and "
         "post3.md; each is under 120 words")


class _Nothing:
    def send(self, *a, **kw):
        return {"ok": True}

    def stop(self, *a, **kw):
        return {"ok": True}


# ── detection ─────────────────────────────────────────────────────────

def test_an_edited_plan_file_is_noticed(config, agent):
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    assert tsk.criteria_drift(agent, t) == [0]


def test_detecting_it_changes_nothing(config, agent):
    """Detection must not be adoption by another name — this is the whole
    reason the file does not simply win."""
    t = _task(config, agent)
    before = list(t.criteria)
    _rewrite(agent, t, SHARP)
    tsk.criteria_drift(agent, t)
    assert t.criteria == before


def test_an_unchanged_plan_has_not_drifted(config, agent):
    t = _task(config, agent)
    assert tsk.criteria_drift(agent, t) == []


def test_an_unreadable_plan_is_not_reported_as_drift(config, agent):
    """A plan that cannot be read is UNKNOWN, and unknown is not changed —
    reporting drift would stop judging on every task with a missing file."""
    t = _task(config, agent)
    _plan_path(agent, t).unlink()
    assert tsk.criteria_drift(agent, t) == []


def test_a_stale_plan_is_exempt(config, agent):
    """It is stale because it no longer describes what happened, and
    `_interact` withheld its criteria deliberately."""
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    t.plan_stale = True
    t.criteria = []
    assert tsk.criteria_drift(agent, t) == []


# ── judging stops until it is settled ─────────────────────────────────

def test_a_drifted_plan_is_not_judged(config, agent):
    """Which of the two criteria is meant is genuinely unknown, and a verdict
    either way answers a question nobody has settled."""
    from ai4science.harness.agents.sarsi import session as ses
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    asked = {}

    def _judge(**kw):
        asked.update(kw)
        return {"state": "PASS", "why": "sure"}

    out = ses.verify(config, agent, t, verifier=_judge, evidence="a listing",
                     runtime=_Nothing())
    assert asked == {}
    assert (out.verdict or {}).get("state") == "UNVERIFIED"


def test_the_refusal_says_how_to_settle_it(config, agent):
    from ai4science.harness.agents.sarsi import session as ses
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    out = ses.verify(config, agent, t, verifier=lambda **kw: {"state": "PASS"},
                     evidence="", runtime=_Nothing())
    assert f"sarsi adopt {agent.id} {t.id}" in (out.verdict or {}).get("why", "")


def test_an_agent_cannot_clear_a_failing_verdict_by_rewriting_its_plan(config,
                                                                       agent):
    """The reason the file does not simply win. The session runs IN the task
    folder and is told `plan0.md` is its plan, so "the file decides" hands the
    thing being judged the power to restate the question and drop the answer."""
    from ai4science.harness.agents.sarsi import session as ses
    t = _task(config, agent)
    tsk.record_phase(config, agent, t, 0, {"state": "FAIL", "why": "no report"})

    _rewrite(agent, t, "anything at all is fine")        # the session rewrites
    ses.verify(config, agent, t, verifier=lambda **kw: {"state": "PASS"},
               evidence="", runtime=_Nothing())

    assert tsk.phase_verdict(t, 0)["state"] == "FAIL"
    assert t.criteria != ["anything at all is fine"]


# ── the owner adopts ──────────────────────────────────────────────────

def test_adopting_takes_the_file_as_the_standard(config, agent):
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    assert tsk.adopt_criteria(agent, t) == [0]
    assert t.criteria == [SHARP]


def test_it_is_persisted(config, agent):
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    tsk.adopt_criteria(agent, t)
    after = [x for x in tsk.all_of(config, agent) if x.id == t.id][0]
    assert after.criteria == [SHARP]


def test_adopting_clears_the_changed_phases_verdict(config, agent):
    """`/edit`'s rule: the phase was judged against a standard that no longer
    exists, and keeping the verdict carries an answer to a question nobody
    asks any more."""
    t = _task(config, agent)
    tsk.record_phase(config, agent, t, 0, {"state": "PASS", "why": "a listing"})
    _rewrite(agent, t, SHARP)
    tsk.adopt_criteria(agent, t)
    assert tsk.phase_verdict(t, 0) is None


def test_an_unchanged_phase_keeps_its_verdict(config, agent):
    """Adopting must not wipe verdicts still about the criterion that earned
    them — otherwise settling one criterion redoes all the finished work."""
    t = _task(config, agent)
    _rewrite(agent, t, "phase one is done", "phase two is done")
    tsk.adopt_criteria(agent, t)
    tsk.record_phase(config, agent, t, 0, {"state": "PASS", "why": "it was"})
    tsk.record_phase(config, agent, t, 1, {"state": "PASS", "why": "it was"})

    _rewrite(agent, t, "phase one is done", "phase two is done DIFFERENTLY")
    assert tsk.adopt_criteria(agent, t) == [1]
    assert tsk.phase_verdict(t, 0) is not None
    assert tsk.phase_verdict(t, 1) is None


def test_changing_the_shape_of_the_plan_clears_every_verdict(config, agent):
    """Phases renumbered: verdict 2 is no longer about phase 2."""
    t = _task(config, agent)
    _rewrite(agent, t, "a", "b")
    tsk.adopt_criteria(agent, t)
    tsk.record_phase(config, agent, t, 0, {"state": "PASS", "why": "it was"})
    tsk.record_phase(config, agent, t, 1, {"state": "PASS", "why": "it was"})

    _rewrite(agent, t, "a")
    tsk.adopt_criteria(agent, t)
    assert t.phase_verdicts == {}


def test_after_adopting_it_judges_again(config, agent):
    from ai4science.harness.agents.sarsi import session as ses
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    tsk.adopt_criteria(agent, t)
    asked = {}

    def _judge(**kw):
        asked.update(kw)
        return {"state": "PASS", "why": "read from disk"}

    ses.verify(config, agent, t, verifier=_judge, evidence="a listing",
               runtime=_Nothing())
    assert SHARP in str(asked.get("criteria"))


# ── and it is visible before you run into it ──────────────────────────

def test_why_reports_the_drift(config, agent):
    """The divergence lasted this long because nothing ever mentioned it."""
    from ai4science.harness.agents.sarsi import why as wy
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    said = wy.explain(config, agent, t)
    assert "adopt" in said and "changed" in said.lower()


def test_why_does_not_adopt_on_your_behalf(config, agent):
    from ai4science.harness.agents.sarsi import why as wy
    t = _task(config, agent)
    before = list(t.criteria)
    _rewrite(agent, t, SHARP)
    wy.explain(config, agent, t)
    assert t.criteria == before


# ── and it is waiting on you ──────────────────────────────────────────

def test_attention_reports_a_drifted_plan(config, agent):
    """`check` refuses until the owner settles it, so the owner has to learn
    that without running `check` first. "What is waiting on me" is that
    command."""
    from ai4science.harness.agents.sarsi import attention as att
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    kinds = [i.kind for i in att.needs(config, agent, live=[]).items]
    assert "drift" in kinds


def test_it_names_the_command_that_settles_it(config, agent):
    from ai4science.harness.agents.sarsi import attention as att
    t = _task(config, agent)
    _rewrite(agent, t, SHARP)
    item = [i for i in att.needs(config, agent, live=[]).items if i.kind == "drift"][0]
    assert item.action == f"sarsi adopt {agent.id} {t.id}"


def test_an_undrifted_task_is_not_waiting_on_you(config, agent):
    from ai4science.harness.agents.sarsi import attention as att
    _task(config, agent)
    assert "drift" not in [i.kind for i in att.needs(config, agent, live=[]).items]
