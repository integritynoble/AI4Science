"""The owner's criterion is the standard, and a re-plan does not replace it.

Three live `work` runs, three failures, none of them in the work. Each time the
session rewrote `plan0.md` into its own phases, and the last one authored an
acceptance criterion nothing could satisfy:

    Verified when: for each of L1, L2, L3, the name on that line matches the
    name at the cited source, character-for-character

There was no cited source — the goal was "write three lines naming the tiers".
The file it produced was exactly right and was failed against a standard the
session had invented for itself, and `retry` could not converge because the
objection was unmeetable rather than unmet.

The design already says what should happen — *"the owner's edit wins; polish may
propose a successor, never replace it"* — and `plan_owner_edited` already
records who authored the criteria. It simply did not hold against a session's
re-plan: `adopt_plan` overwrote `task.criteria` from whatever the session had
just written, and the owner's standard was gone.

  * **an owner-authored criterion survives.** The session may rewrite its steps,
    its notes and its phases; what a verdict is measured against stays the
    owner's until the owner changes it.
  * **the file is still reported.** Silently ignoring the session's rewrite
    would hide that the plan on disk no longer describes what is being judged —
    so `why` says so, and says whose standard stands.
  * **judging is not refused for it.** Drift refuses when nobody has said which
    of the two is meant. Here somebody has: the owner.
  * **the owner can still change their mind.** `sarsi adopt` is an explicit act
    and still takes the file — including the session's version of it.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             worker)


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


OWNERS = "notes.md exists and names L1, L2 and L3."
SESSIONS = "each name matches the cited source character-for-character."


def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="name the three tiers")
    return tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                           pl.draft(d))


def _write_plan(agent, t, criterion):
    (tsk.dir_of(agent, t.id) / f"{t.plan_version}.md").write_text(
        f"# {t.goal}\n\n## Phase 1 — do it\nVerified when: {criterion}\n")


def _owner_sets(config, agent, t, criterion=OWNERS):
    """What the owner does: sharpen the plan file, then adopt it."""
    _write_plan(agent, t, criterion)
    tsk.adopt_criteria(agent, t)
    return t


# ── the owner's act is recorded as the owner's ────────────────────────

def test_adopting_marks_the_criteria_as_the_owners(config, agent):
    """`adopt` is the owner saying what the standard is. Without recording that,
    nothing downstream can tell their criterion from a session's."""
    t = _owner_sets(config, agent, _task(config, agent))
    assert t.plan_owner_edited is True


def test_a_session_written_plan_is_not_the_owners(config, agent):
    t = _task(config, agent)
    _write_plan(agent, t, SESSIONS)
    tsk.adopt_plan(config, agent, t, pl.parse(
        (tsk.dir_of(agent, t.id) / "plan0.md").read_text()))
    assert t.plan_owner_edited is False


# ── and it survives the re-plan ───────────────────────────────────────

def test_the_session_re_planning_does_not_replace_it(config, agent):
    """The live failure, in one line."""
    t = _owner_sets(config, agent, _task(config, agent))
    _write_plan(agent, t, SESSIONS)              # the session rewrites it
    tsk.adopt_plan(config, agent, t, pl.parse(
        (tsk.dir_of(agent, t.id) / "plan0.md").read_text()))
    assert t.criteria == [OWNERS]


def test_and_the_verdict_is_measured_against_the_owners(config, agent):
    t = _owner_sets(config, agent, _task(config, agent))
    _write_plan(agent, t, SESSIONS)
    seen = {}

    def _judge(**kw):
        seen.update(kw)
        return {"state": "PASS", "why": "fine"}

    ses.verify(config, agent, t, verifier=_judge, evidence="a listing",
               runtime=_Nothing())
    assert seen.get("criteria") == [OWNERS]


def test_judging_is_not_refused_for_the_difference(config, agent):
    """Drift refuses when nobody has said which of the two is meant. Here
    somebody has."""
    t = _owner_sets(config, agent, _task(config, agent))
    _write_plan(agent, t, SESSIONS)
    out = ses.verify(config, agent, t, verifier=lambda **kw: {"state": "PASS",
                                                             "why": "fine"},
                     evidence="e", runtime=_Nothing())
    assert (out.verdict or {}).get("state") == "PASS"


def test_a_task_with_no_owner_criterion_still_refuses(config, agent):
    """Unchanged where nobody has decided: the session rewrote the plan and no
    owner has said which standard applies."""
    t = _task(config, agent)
    _write_plan(agent, t, SESSIONS)
    out = ses.verify(config, agent, t, verifier=lambda **kw: {"state": "PASS"},
                     evidence="e", runtime=_Nothing())
    assert (out.verdict or {}).get("state") == "UNVERIFIED"
    assert "adopt" in (out.verdict or {}).get("why", "")


# ── the difference is still reported ──────────────────────────────────

def test_why_says_the_file_differs_and_whose_standard_stands(config, agent):
    """Ignoring the rewrite silently would hide that the plan on disk no longer
    describes what is being judged."""
    from ai4science.harness.agents.sarsi import why as wy
    t = _owner_sets(config, agent, _task(config, agent))
    _write_plan(agent, t, SESSIONS)
    said = wy.explain(config, agent, t)
    assert "yours" in said.lower() or "owner" in said.lower()
    assert OWNERS in said


def test_the_owner_can_still_take_the_sessions_version(config, agent):
    """`adopt` is an explicit act and still means what it says."""
    t = _owner_sets(config, agent, _task(config, agent))
    _write_plan(agent, t, SESSIONS)
    tsk.adopt_criteria(agent, t)
    assert t.criteria == [SESSIONS]


class _Nothing:
    def send(self, *a, **kw):
        return {"ok": True}

    def stop(self, *a, **kw):
        return {"ok": True}


# ── a plan that cannot be parsed is reported, not raised ──────────────

def _write_bad_plan(agent, t):
    """What a session actually wrote: a phase with no `Verified when:` line."""
    (tsk.dir_of(agent, t.id) / f"{t.plan_version}.md").write_text(
        f"# {t.goal}\n\n"
        f"## Phase 1 — do it\nVerified when: {OWNERS}\n\n"
        f"## Phase 2 — independent check of the file's contents\n"
        f"Re-read it and confirm.\n")


def test_why_reports_an_unparseable_plan_instead_of_crashing(config, agent):
    """Caught live. `why` is the command you reach for when the rest is not
    trusted, and it died on a traceback:

        BadPlan: phase "independent check of the file's contents" has no
        `Verified when:` line

    The session had written that phase. Raising there means the one command
    that explains what is going on is the one that cannot run when something is
    wrong — and it takes the goal, the verdict and the criteria down with it."""
    from ai4science.harness.agents.sarsi import why as wy
    t = _owner_sets(config, agent, _task(config, agent))
    _write_bad_plan(agent, t)
    said = wy.explain(config, agent, t)
    assert "verified when" in said.lower()
    assert "cannot be read" in said.lower() or "could not be read" in said.lower()


def test_and_still_says_what_it_knows(config, agent):
    """The record holds the goal, the criteria and the verdict. A broken file on
    disk is no reason to withhold them."""
    from ai4science.harness.agents.sarsi import why as wy
    t = _owner_sets(config, agent, _task(config, agent))
    t.verdict = {"state": "FAIL", "why": "nothing was written"}
    _write_bad_plan(agent, t)
    said = wy.explain(config, agent, t)
    assert OWNERS in said
    assert "nothing was written" in said


def test_the_plan_command_survives_it_too(config, agent):
    """`sarsi plan` renders the same file."""
    from ai4science.harness.agents.sarsi import task as _t
    t = _owner_sets(config, agent, _task(config, agent))
    _write_bad_plan(agent, t)
    assert _t.read_plan_or_none(config, agent, t) is None
