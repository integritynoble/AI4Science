"""What the owner released is the standard. A later edit does not stop the run.

Two live runs in a row ended the same way: the work was correct, the session had
edited `plan0.md` while doing it, and `check` refused —

    UNVERIFIED: plan0.md no longer matches the criteria this task was attached
    with — phase 2 reads differently. … Take the file as the standard with
    `sarsi adopt sarsi-worker tsk_f3493bae71`

Sessions revising their own plan mid-work is routine, not exceptional. So the
refusal fires on most tasks, and what it asks the owner to do is **adopt
whatever the session just wrote** — in order to unblock. An owner who wants the
run to finish will adopt without reading, and a gate that is habitually
rubber-stamped has become a worse thing than no gate: it launders the session's
rewrite as the owner's decision.

The refusal already has an exemption, and its reasoning is the whole answer:

    Refused only when nobody has said which of the two is meant. When the OWNER
    authored the criteria, somebody has.

**Granting and releasing is somebody saying so.** The owner reads the plan, grants
each permission it declared, and raises the ceiling — against *that* standard,
the one in the record. A file edited afterwards is not a competing reading of an
open question; it is the session's working copy moving after the question was
answered. So:

  * **before release** — nothing has been approved, the ambiguity is real, and
    judging is refused exactly as before.
  * **after release** — the recorded criteria are the standard, judging proceeds,
    and the divergence is REPORTED on the verdict rather than silently dropped.
    `adopt` still exists, and now it is a thing the owner chooses rather than a
    toll they pay.

The property that must not move: **a session cannot lower its own bar.** The plan
file lives in the session's own working directory. Judging against the record is
what denies it that; the old refusal denied it too, but only by stopping, and
stopping is what made the owner adopt.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)

PLAN = """# write the report

## Phase 1 — write it
Do the thing.
Verified when: out.txt exists and contains 42

## Permissions needed
- none
"""

#: the same plan with the criterion rewritten — what a session does mid-work
REWRITTEN = PLAN.replace("out.txt exists and contains 42",
                         "out.txt exists")


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


class Runtime:
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
        return {}


def _passing(**kw):
    return {"state": "PASS", "why": "out.txt is there and says 42"}


def _task(config, agent, *, released):
    d = wk.Directive(agent_id=agent.id, goal="write the report")
    t = tsk.create(config, agent, d)
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(PLAN)
    t = tsk.attach_plan(config, agent, t, pl.parse(PLAN))
    t.plan_agreed = True
    t = ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())
    if released:
        t.work_started_at = time.time()
    tsk._touch(agent, t, time.time)
    return t


def _rewrite(agent, t):
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(REWRITTEN)


# ── after the owner released, judging proceeds ────────────────────────

def test_a_released_task_is_judged_against_what_was_released(config, agent):
    t = _task(config, agent, released=True)
    _rewrite(agent, t)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="out.txt: 42",
                   runtime=Runtime(), now=time.time)
    assert t.verdict["state"] == "PASS"


def test_and_the_verdict_says_the_file_has_since_changed(config, agent):
    """Judged is not the same as unnoticed. A verdict that said nothing would
    leave the owner reading a PASS against a criterion the file no longer
    shows."""
    t = _task(config, agent, released=True)
    _rewrite(agent, t)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="out.txt: 42",
                   runtime=Runtime(), now=time.time)
    # The refusal message ALSO contains these words, so the verdict is pinned
    # first: without this the test passes against the behaviour it replaces.
    assert t.verdict["state"] == "PASS"
    why = (t.verdict.get("why") or "").lower()
    assert "plan0.md" in why or "changed" in why
    assert "adopt" in why


def test_the_standard_is_the_record_not_the_file(config, agent):
    """The property that must not move. The rewritten file drops `contains 42`;
    what is judged still has it."""
    t = _task(config, agent, released=True)
    _rewrite(agent, t)
    seen = {}

    def spy(**kw):
        seen.update(kw)
        return {"state": "PASS", "why": "ok"}

    ses.verify(config, agent, t, verifier=spy, evidence="e", runtime=Runtime(),
               now=time.time)
    judged = " ".join(seen.get("criteria") or [])
    assert "42" in judged, seen


def test_a_session_cannot_lower_its_own_bar(config, agent):
    """The whole reason the refusal existed. A file rewritten to something the
    work DOES meet must not turn a failing task into a passing one."""
    t = _task(config, agent, released=True)
    _rewrite(agent, t)                       # criterion relaxed to "out.txt exists"

    def strict(**kw):
        crit = " ".join(kw.get("criteria") or [])
        return ({"state": "FAIL", "why": "no 42 in the file"} if "42" in crit
                else {"state": "PASS", "why": "it exists"})

    t = ses.verify(config, agent, t, verifier=strict, evidence="out.txt: 7",
                   runtime=Runtime(), now=time.time)
    assert t.verdict["state"] == "FAIL"


# ── before release, nothing has been approved ─────────────────────────

def test_an_unreleased_task_still_refuses(config, agent):
    """No grant, no release, nobody has said which of the two is meant."""
    t = _task(config, agent, released=False)
    _rewrite(agent, t)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=Runtime(), now=time.time)
    assert t.verdict["state"] == "UNVERIFIED"
    assert "adopt" in (t.verdict.get("why") or "")


def test_the_owner_s_own_edit_is_still_exempt(config, agent):
    """Unchanged: when the owner authored the criteria the question is already
    answered, released or not."""
    t = _task(config, agent, released=False)
    t.plan_owner_edited = True
    _rewrite(agent, t)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=Runtime(), now=time.time)
    assert t.verdict["state"] == "PASS"


# ── and an undrifted task says nothing about drift ────────────────────

def test_a_plan_nobody_touched_carries_no_note(config, agent):
    t = _task(config, agent, released=True)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="e",
                   runtime=Runtime(), now=time.time)
    assert "adopt" not in (t.verdict.get("why") or "")


# ── the per-phase path says it too ────────────────────────────────────

def test_a_phase_verdict_carries_the_same_note(config, agent):
    """`supervise` judges the phase the work is ON, not the task as a whole, so
    a note that only reached the whole-task path would be missing from almost
    every verdict the loop actually produces."""
    t = _task(config, agent, released=True)
    _rewrite(agent, t)
    t = ses.verify(config, agent, t, verifier=_passing, evidence="out.txt: 42",
                   runtime=Runtime(), phase=0, now=time.time)
    got = t.phase_verdicts.get("0") or {}
    assert got.get("state") == "PASS"
    assert "adopt" in (got.get("why") or "").lower()


# ── and the owner is told without being blocked ───────────────────────

def test_attention_no_longer_says_judging_is_refused(config, agent):
    """It was true and is not any more. A board that still said it would send
    the owner to `adopt` to unblock a run that is not blocked."""
    from ai4science.harness.agents.sarsi import attention as att
    t = _task(config, agent, released=True)
    _rewrite(agent, t)
    items = [i for i in att.needs(config, agent, pane=_Pane(),
                                  live=lambda: set()).items if i.kind == "drift"]
    assert items, "the owner should still be told the file moved"
    assert "refused" not in items[0].detail.lower()


def test_but_an_unreleased_one_still_says_so(config, agent):
    from ai4science.harness.agents.sarsi import attention as att
    t = _task(config, agent, released=False)
    _rewrite(agent, t)
    items = [i for i in att.needs(config, agent, pane=_Pane(),
                                  live=lambda: set()).items if i.kind == "drift"]
    assert items and "refused" in items[0].detail.lower()


class _Pane:
    def capture(self, name):
        return "❯ \n"
