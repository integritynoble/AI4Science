"""Three defects a live run found, that the tests had not.

They share a shape: the system knew the right answer and did not act on it.

  1. **`supervise` spun on an attended agent.** `tick` already returns
     `attended` — "this loop cannot read that interface" — and `run` did not
     treat it as terminal, so it re-derived the same static fact twelve times at
     twenty seconds apiece. A fact that cannot change by waiting is not worth
     waiting for; four minutes of it reads as a hang, which is how it was found.
  2. **The task stayed at `planning`** after the session had done the work and
     written its report, because on an attended agent nothing advances it. The
     record then says a thing that did not happen.
  3. **A new roster agent could not reach a machine that was already
     initialised.** `init` refuses when a config exists and says "edit it" —
     which is the owner hand-editing JSON to get an agent the release already
     shipped.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (admin, operator as op,
                                             registry as reg, task as tsk)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(isolated):
    admin.init(owner_id="7007143162")
    return reg.load()


# ── 1. a loop that cannot read the screen stops saying so ─────────────

class _Pane:
    """Reading an attended pane is fine; TYPING at one is the danger.

    The loop's own comment says why: blind keystrokes are input to whatever menu
    happens to be showing, and on this TUI they once walked the cursor onto
    "No, exit" and killed the session being supervised. So `capture` answers
    like the real pane and `send` is the one that must never be reached.
    """
    def capture(self, name):
        return ""

    def send(self, name, text):                  # pragma: no cover
        raise AssertionError("an attended session must not be typed at")


def _attended_task(config):
    agent = config.agents["computational-imaging"]
    t = tsk.create(config, agent, tsk.Directive(agent_id=agent.id, goal="state the convention"))
    t.session = {"name": "computational-imaging-test"}
    return agent, t


def test_supervising_an_attended_agent_stops_on_the_first_pass(config):
    """The defect: twelve passes and 240 seconds to learn something true before
    the first one."""
    agent, t = _attended_task(config)
    slept = []
    actions = op.run(config, agent, t, pane=_Pane(), passes=12, interval=20.0,
                     sleep=slept.append)
    assert [a.kind for a in actions] == ["attended"]
    assert slept == [], "it waited for a fact that cannot change by waiting"


def test_and_says_what_the_owner_should_do_instead(config):
    """Refusing without a next step leaves the owner with a stopped loop and no
    route — which is how the task sat at `planning` with the work finished."""
    agent, t = _attended_task(config)
    detail = op.run(config, agent, t, pane=_Pane(), passes=3, interval=0.0,
                    sleep=lambda s: None)[0].detail
    assert "tmux attach" in detail
    assert "sarsi check" in detail, (
        "the owner drives an attended agent, so the verdict route is theirs and "
        "has to be named where the loop gives up")


def test_a_drivable_agent_is_unaffected(config):
    """The guard is drivability, not a special case for one agent."""
    from ai4science.harness.agents.sarsi import session as ses
    assert ses.drivable(config.agents["sarsi-worker"].spec)
    assert not ses.drivable(config.agents["computational-imaging"].spec)


# ── 3. a new roster agent reaches a machine already initialised ───────

def test_init_still_refuses_to_overwrite_a_registry(config, isolated):
    """The refusal is right and stays. What was missing was the other half."""
    with pytest.raises(admin.AlreadyInitialised):
        admin.init(owner_id="7007143162")


def test_reconcile_adds_a_roster_agent_the_release_shipped(config, isolated):
    """The live case: `computational-imaging` was added to `_ROSTER`, grace's
    machine had been initialised months earlier, and the only route was editing
    JSON by hand."""
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    raw["agents"]["list"] = [a for a in raw["agents"]["list"]
                             if a["id"] != "computational-imaging"]
    path.write_text(json.dumps(raw))

    added = admin.reconcile()
    assert added == ["computational-imaging"]
    assert "computational-imaging" in reg.load().agents


def test_and_it_gives_the_new_agent_its_bindings_and_account(config, isolated):
    """An agent with no binding is unreachable, which is the failure the
    registry's own startup refusal exists to prevent."""
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    raw["agents"]["list"] = [a for a in raw["agents"]["list"]
                             if a["id"] != "computational-imaging"]
    raw["bindings"] = [b for b in raw["bindings"]
                       if b["agentId"] != "computational-imaging"]
    del raw["channels"]["telegram"]["accounts"]["computational-imaging"]
    path.write_text(json.dumps(raw))

    admin.reconcile()
    c = reg.load()
    assert c.resolve("cli", "computational-imaging") == "computational-imaging"
    assert c.resolve("telegram", "computational-imaging") == "computational-imaging"


def test_it_creates_the_new_agents_directories(config, isolated):
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    raw["agents"]["list"] = [a for a in raw["agents"]["list"]
                             if a["id"] != "computational-imaging"]
    path.write_text(json.dumps(raw))
    admin.reconcile()
    assert reg.load().agents["computational-imaging"].workspace.is_dir()


def test_reconciling_twice_adds_nothing(config):
    assert admin.reconcile() == []


def test_it_never_removes_or_rewrites_what_is_already_there(config, isolated):
    """Additive only. An agent the owner retired, renamed or re-ceilinged is
    theirs; a reconcile that "fixed" those would undo the owner's decisions to
    match a default — and it would do it silently, on upgrade."""
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    for a in raw["agents"]["list"]:
        if a["id"] == "social":
            a["ceiling"] = "A3"
            a["about"] = ["only what I said"]
    raw["agents"]["list"].append({"id": "mine", "role": "worker",
                                  "spec": "claude-code"})
    path.write_text(json.dumps(raw))

    admin.reconcile()
    after = json.loads(path.read_text())
    social = [a for a in after["agents"]["list"] if a["id"] == "social"][0]
    assert social["ceiling"] == "A3"
    assert social["about"] == ["only what I said"]
    assert any(a["id"] == "mine" for a in after["agents"]["list"])


def test_and_the_owner_is_told_what_it_added(config, isolated):
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    raw["agents"]["list"] = [a for a in raw["agents"]["list"]
                             if a["id"] != "computational-imaging"]
    path.write_text(json.dumps(raw))
    from typer.testing import CliRunner
    from ai4science.cli import app
    out = CliRunner().invoke(app, ["sarsi", "init", "--reconcile"]).output
    assert "computational-imaging" in out


# ── 2. the record says what happened, on an attended agent too ────────

def _verifier(state="PASS", why="the report is there with citations"):
    return lambda **kw: {"state": state, "why": why}


def test_judging_an_attended_task_moves_it_out_of_planning(config):
    """The live shape: the session did the work and wrote its report, the loop
    could not read the pane, and `sarsi tasks` went on saying `planning`. A
    record that says a thing which did not happen is worse than no record."""
    from ai4science.harness.agents.sarsi import session as ses
    agent, t = _attended_task(config)
    assert t.state == tsk.PLANNING
    t = ses.verify(config, agent, t, verifier=_verifier(),
                   evidence="cassi_convention_report.md — 3 claims, each cited")
    assert t.state != tsk.PLANNING
    assert t.state == tsk.VERIFIED


def test_and_a_failed_judgement_does_not_leave_it_reading_planning(config):
    """FAIL is an outcome. Planning is not."""
    from ai4science.harness.agents.sarsi import session as ses
    agent, t = _attended_task(config)
    t = ses.verify(config, agent, t, verifier=_verifier("FAIL", "no citations"),
                   evidence="a paragraph of prose")
    assert t.state != tsk.PLANNING


def test_the_verdict_records_that_a_person_drove_it(config):
    """On an attended agent the owner is in the loop by construction, and the
    record should be able to say so — a verdict that cannot say who reached it
    is one voice with several names."""
    from ai4science.harness.agents.sarsi import session as ses
    agent, t = _attended_task(config)
    t = ses.verify(config, agent, t, verifier=_verifier(), engine="owner",
                   evidence="the report")
    assert (t.verdict or {}).get("engine") == "owner"


# ── 4. evidence that is a listing is not evidence ─────────────────────

def test_a_written_deliverable_is_read_not_just_listed(tmp_path):
    """Found by following the fix above to its end: `check` on the real attended
    task returned FAIL because the evidence gathered was a directory listing.

    The verifier was right — "the mere existence of a file named
    cassi_convention_report is a claim that work was done, not evidence of its
    content" — and the gatherer was wrong. It reads files NAMED IN THE CRITERIA,
    and a task with no plan has no criteria, so a report can never pass however
    good it is.
    """
    from ai4science.harness.agents.sarsi import evidence as evd
    (tmp_path / "report.md").write_text("mask: binary {0,1} — generate_data.py:51")
    got = evd.gather(tmp_path, [])
    assert "generate_data.py:51" in got, "the listing was gathered, not the work"


def test_the_named_file_still_wins_when_a_criterion_names_one(tmp_path):
    """The existing path is the precise one and stays first."""
    from ai4science.harness.agents.sarsi import evidence as evd
    (tmp_path / "wanted.md").write_text("THE ANSWER")
    (tmp_path / "other.md").write_text("something else")
    got = evd.gather(tmp_path, ["produces wanted.md with the answer"])
    assert "THE ANSWER" in got


def test_it_does_not_read_without_limit(tmp_path):
    """A gatherer that pastes a whole working tree into a prompt has replaced
    one failure with a more expensive one."""
    from ai4science.harness.agents.sarsi import evidence as evd
    for i in range(40):
        (tmp_path / f"f{i}.md").write_text("x" * 20_000)
    got = evd.gather(tmp_path, [])
    assert len(got) < 200_000


def test_and_says_what_it_left_out(tmp_path):
    """Unknown is not zero. Evidence silently truncated reads as evidence that
    was not there."""
    from ai4science.harness.agents.sarsi import evidence as evd
    for i in range(40):
        (tmp_path / f"f{i}.md").write_text("x" * 20_000)
    got = evd.gather(tmp_path, [])
    assert "not read" in got.lower() or "omitted" in got.lower() or "truncat" in got.lower()


def test_an_empty_folder_still_says_it_is_empty(tmp_path):
    """The distinction the module already draws must survive the change."""
    from ai4science.harness.agents.sarsi import evidence as evd
    got = evd.gather(tmp_path, [])
    assert got.strip(), "an empty folder is a fact, not an empty string"


# ── 5. release says why, instead of printing the state back ───────────

def test_releasing_a_task_whose_plan_was_never_collected_says_so(config):
    """Live: `sarsi release` on a task still in `planning` printed
    "tsk_… — planning" and did nothing. `task.start` returns unchanged unless
    the state is READY or OFF, so the owner was handed back the state they
    already knew, with no hint of the missing step.

    The missing step is that the session drafted a plan and nothing attached it
    to the task record — which is `sarsi supervise`'s job. Every other refusal
    in this file names its route; this one printed a noun.
    """
    from ai4science.harness.agents.sarsi import session as ses
    agent = config.agents["sarsi-worker"]
    t = tsk.create(config, agent, tsk.Directive(agent_id=agent.id, goal="count files"))
    assert t.state == tsk.PLANNING
    with pytest.raises(ses.NotReady) as e:
        ses.release(config, agent, t)
    assert "plan" in str(e.value).lower()
    assert "sarsi supervise" in str(e.value)


def test_the_existing_awaiting_grant_refusal_is_unchanged(config):
    """It already named what it waited on, and it keeps its own wording."""
    from ai4science.harness.agents.sarsi import session as ses
    agent = config.agents["sarsi-worker"]
    t = tsk.create(config, agent, tsk.Directive(agent_id=agent.id, goal="count files"))
    t.state = tsk.AWAITING_GRANT
    t.awaiting = ["read-only shell"]
    with pytest.raises(ses.NotReady, match="read-only shell"):
        ses.release(config, agent, t)


def test_a_granted_ready_task_still_releases(config):
    """The fix must not turn a working path into a refusal."""
    from ai4science.harness.agents.sarsi import session as ses
    agent = config.agents["sarsi-worker"]
    t = tsk.create(config, agent, tsk.Directive(agent_id=agent.id, goal="count files"))
    t.state = tsk.READY
    t = ses.release(config, agent, t)
    assert t.state == tsk.RUNNING
    assert t.released_at is not None


# ── 6. a question only the owner can answer stops the loop ────────────

class _AskingPane:
    """A session sitting on a question the plan does not settle."""
    def __init__(self):
        self.sent = []

    def capture(self, name):
        return ("I need one thing from you before I can finish:\n"
                "update that one line in the plan to match your chosen string?")

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}


def test_a_question_only_the_owner_can_settle_ends_the_run(config, monkeypatch):
    """Live on grace: the loop reported `asks-owner` on six consecutive passes —
    the same sentence each time — and spent its whole budget while the work was
    already done and sitting in the folder.

    `awaiting-grant` is already terminal for exactly this reason. A question the
    loop has decided it cannot answer is the same shape: it changes when the
    OWNER acts, which is not something another pass brings closer.
    """
    agent = config.agents["sarsi-worker"]
    t = tsk.create(config, agent, tsk.Directive(agent_id=agent.id, goal="count files"))
    t.session = {"name": "sarsi-worker-test"}
    t.state = tsk.RUNNING

    monkeypatch.setattr(op, "tick",
                        lambda *a, **k: op.Action("asks-owner", "needs you"))
    slept = []
    actions = op.run(config, agent, t, pane=_AskingPane(), passes=6,
                     interval=12.0, sleep=slept.append)
    assert [a.kind for a in actions] == ["asks-owner"]
    assert slept == []


def test_but_ordinary_progress_still_uses_every_pass(config, monkeypatch):
    """The guard is that one kind, not a general shortening of the loop."""
    agent = config.agents["sarsi-worker"]
    t = tsk.create(config, agent, tsk.Directive(agent_id=agent.id, goal="count files"))
    t.session = {"name": "sarsi-worker-test"}
    monkeypatch.setattr(op, "tick",
                        lambda *a, **k: op.Action("steered", "kept going"))
    actions = op.run(config, agent, t, pane=_AskingPane(), passes=4,
                     interval=0.0, sleep=lambda s: None)
    assert len(actions) == 4
