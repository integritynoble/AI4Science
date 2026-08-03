"""`ASG` — the worker hands the **plan** to `sarsi-claude`.

This is the seam. Below it the 27-node session loop runs unchanged; above it the
only rules that matter are: a worker does this and nothing else may; the session
is handed the plan rather than the wish; one task gets one session; and the
verdict comes back from a verifier, never from the agent that did the work.

Every outside call — starting tmux, typing into the pane, asking a model — is an
injected seam, so these rules are asserted against real code without a terminal.
"""
import json
from dataclasses import asdict

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
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
    """Stands in for tmux + Claude Code. Records what it was asked to do."""

    def __init__(self, *, ok=True):
        self.ok = ok
        self.started = []
        self.sent = []

    def start(self, name, cwd, *, govern, ceiling, env=None):
        self.started.append({"name": name, "cwd": cwd, "govern": govern,
                             "ceiling": ceiling, "env": dict(env or {})})
        if not self.ok:
            return {"ok": False, "reason": "could not start tmux session"}
        return {"ok": True, "name": name, "pid": 4242, "cwd": cwd,
                "target": f"{name}:0.0"}

    def send(self, name, text):
        self.sent.append((name, text))
        return {"ok": True}


def _plan(permissions=(), phases=None):
    return pl.Plan(goal="finish the export",
                   phases=phases or [
                       pl.Phase(title="drain the queue",
                                verified_when="the queue length reads 0"),
                       pl.Phase(title="re-run the export",
                                verified_when="export.csv has 1,204 rows")],
                   permissions=list(permissions))


def _task(config, agent, permissions=()):
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), _plan(permissions))
    return tsk.start(config, agent, t)


# ── who may assign ────────────────────────────────────────────────────

def test_only_a_worker_may_assign(config):
    """ASG may not be performed by anything other than a worker."""
    machine = config.agents["sarsi-machine"]
    with pytest.raises(worker.NotAWorker):
        ses.assign(config, machine, tsk.Task(id="tsk_x", agent_id=machine.id,
                                             goal="g"), runtime=FakeRuntime())


def test_a_task_still_awaiting_a_grant_is_not_assigned(config, agent):
    t = _task(config, agent, permissions=["write /home/me/reports"])
    rt = FakeRuntime()
    with pytest.raises(ses.NotReady, match="write /home/me/reports"):
        ses.assign(config, agent, t, runtime=rt)
    assert rt.started == []


# ── one task, one session ─────────────────────────────────────────────

def test_assign_starts_one_session_for_this_task(config, agent):
    t = ses.assign(config, agent, _task(config, agent), runtime=FakeRuntime())
    assert t.session["name"].startswith("work-")
    assert t.id[-4:] in t.session["name"]


def test_assigning_twice_reuses_the_same_session(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    again = ses.assign(config, agent, t, runtime=rt)
    assert again.session["name"] == t.session["name"]
    assert len(rt.started) == 1          # one task, one session


def test_two_tasks_do_not_share_a_session(config, agent):
    rt = FakeRuntime()
    a = ses.assign(config, agent, _task(config, agent), runtime=rt)
    b = ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert a.session["name"] != b.session["name"]


def test_the_session_is_governed_at_the_agents_ceiling(config, agent):
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.started[0]["govern"] is True
    assert rt.started[0]["ceiling"] == agent.ceiling


# ── the ceiling an agent actually gets ────────────────────────────────

@pytest.fixture
def trust_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path / "cp"))
    monkeypatch.setenv("PWM_TRUST_OWNER", "tester")
    from ai4science.harness.agents.machine import trust
    return trust


def test_a_configured_a3_is_capped_until_it_is_earned(config, agent, trust_ledger):
    """`A3 is earned, not set.` Writing it in the registry must not be a way to
    hand an agent full autonomy by editing a file."""
    agent.ceiling = "A3"
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.started[0]["ceiling"] == "A2"


def test_the_task_records_the_ceiling_it_actually_got(config, agent, trust_ledger):
    """Recording the requested one would make the board lie about what is
    running."""
    agent.ceiling = "A3"
    t = ses.assign(config, agent, _task(config, agent), runtime=FakeRuntime())
    assert t.session["ceiling"] == "A2"
    assert t.session["ceiling_requested"] == "A3"


def test_a2_needs_no_earning(config, agent, trust_ledger):
    agent.ceiling = "A2"
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.started[0]["ceiling"] == "A2"


def test_an_earned_a3_passes_through(config, agent, trust_ledger):
    trust_ledger.unlock_a3(force=True)
    agent.ceiling = "A3"
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.started[0]["ceiling"] == "A3"


def test_each_agent_carries_its_own_ceiling(config, trust_ledger):
    work, abraham = config.agents["work"], config.agents["abraham"]
    work.ceiling, abraham.ceiling = "A2", "A0"
    rt = FakeRuntime()
    ses.assign(config, work, _task(config, work), runtime=rt)
    ses.assign(config, abraham, _task(config, abraham), runtime=rt)
    assert [s["ceiling"] for s in rt.started] == ["A2", "A0"]


def test_a_session_that_will_not_start_is_reported_not_pretended(config, agent):
    rt = FakeRuntime(ok=False)
    t = _task(config, agent)
    with pytest.raises(ses.CouldNotStart, match="tmux"):
        ses.assign(config, agent, t, runtime=rt)
    assert tsk.get(config, agent, t.id).session is None


# ── VLT sits between the grant and the session ────────────────────────

def _secret_task(config, agent):
    from ai4science.harness.agents.sarsi import vault
    vault.put(config, "mail.read", "hunter2")
    d = worker.Directive(agent_id=agent.id, goal="triage the mailbox",
                         requires_secrets=["mail.read"])
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), _plan())
    t = tsk.grant(config, agent, t, "read secret mail.read")
    return tsk.start(config, agent, t)


def test_a_denied_secret_stops_the_task_before_any_session_starts(config, agent):
    rt = FakeRuntime()
    t = _secret_task(config, agent)
    with pytest.raises(ses.NotReady, match="mail.read"):
        ses.assign(config, agent, t, runtime=rt,
                   vault_prompt=lambda **kw: "no")
    assert rt.started == []


def test_an_allowed_secret_reaches_the_runtime_and_nothing_else(config, agent):
    """On allow the value goes to the local session and nowhere else — not the
    task record, not the plan, not a ledger."""
    from ai4science.harness.agents.sarsi import ledger
    rt = FakeRuntime()
    t = ses.assign(config, agent, _secret_task(config, agent), runtime=rt,
                   vault_prompt=lambda **kw: "yes")
    assert rt.started[0]["env"]["mail.read"] == "hunter2"
    assert "hunter2" not in json.dumps(asdict(t))
    assert "hunter2" not in json.dumps(ledger.read(config, "vault"))
    assert "hunter2" not in (tsk.dir_of(agent, t.id) / "plan0.md").read_text()


def test_a_task_needing_no_secret_never_asks(config, agent):
    asked = []
    ses.assign(config, agent, _task(config, agent), runtime=FakeRuntime(),
               vault_prompt=lambda **kw: asked.append(kw))
    assert asked == []


# ── it is handed the PLAN, not the wish ───────────────────────────────

def test_the_kickoff_names_the_plan_file(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    text = rt.sent[0][1]
    assert "plan0.md" in text


def test_the_kickoff_names_the_earliest_incomplete_phase(config, agent):
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert "drain the queue" in rt.sent[0][1]


def test_the_kickoff_does_not_carry_the_conversation(config, agent):
    """What crosses is what the session needs, never the transcript of how it
    was asked — that is what keeps the session's context bounded."""
    from ai4science.harness.agents.sarsi import ownerlog
    ownerlog.append(config, agent, "and by the way my cat is called Mildred",
                    surface="cli")
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert "Mildred" not in rt.sent[0][1]


# ── the verdict comes from a verifier ─────────────────────────────────

def test_the_verifier_is_given_the_plans_criteria(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    seen = {}

    def verifier(*, goal, criteria, evidence):
        seen.update(goal=goal, criteria=criteria)
        return {"state": "PASS"}

    ses.verify(config, agent, t, verifier=verifier, evidence="the screen")
    assert seen["criteria"] == ["the queue length reads 0",
                                "export.csv has 1,204 rows"]


def test_a_stale_plans_criteria_are_withheld_from_the_verifier(config, agent):
    """Judging this run against a superseded mission's standard is worse than
    judging against the goal alone."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t.criteria = []                      # what a stale plan yields
    seen = {}

    def verifier(*, goal, criteria, evidence):
        seen.update(criteria=criteria)
        return {"state": "PASS"}

    ses.verify(config, agent, t, verifier=verifier, evidence="")
    assert seen["criteria"] == [] and seen != {}


def test_a_pass_verifies_the_task_and_records_the_verdict(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.verify(config, agent, t, evidence="rows: 1204",
                   verifier=lambda **kw: {"state": "PASS", "why": "counted"})
    assert t.state == tsk.VERIFIED and t.verdict["state"] == "PASS"


def test_a_fail_leaves_the_task_running_and_feeds_the_reason_back(config, agent):
    """FAIL's reason is used, not just logged."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.verify(config, agent, t, evidence="rows: 3", runtime=rt,
                   verifier=lambda **kw: {"state": "FAIL", "why": "only 3 rows"})
    assert t.state == tsk.RUNNING
    assert "only 3 rows" in rt.sent[-1][1]


def test_an_undelivered_reason_is_recorded_as_undelivered(config, agent):
    """FAIL's reason is used, not just logged — so when it could not be
    delivered into the session, that is a fact the record must carry rather
    than a steer everyone assumes happened."""
    from ai4science.harness.agents.sarsi import ledger

    class DeadPane(FakeRuntime):
        def send(self, name, text):
            raise RuntimeError("no such session")

    rt = DeadPane()
    t = ses.assign(config, agent, _task(config, agent), runtime=FakeRuntime())
    ses.verify(config, agent, t, evidence="rows: 3", runtime=rt,
               verifier=lambda **kw: {"state": "FAIL", "why": "only 3 rows"})
    assert ledger.read(config, "reports")[-1]["steered"] is False


def test_an_unverified_result_steers_nothing_into_the_session(config, agent):
    """The bug this exists for: with no verifier configured, the session was
    told "the verifier says this is not done yet: no independent verifier is
    available" and asked to address it — a correction nobody made, about a
    problem the session cannot fix."""
    from ai4science.harness.agents.sarsi import verifier as vf
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    before = len(rt.sent)
    t = ses.verify(config, agent, t, evidence="the screen", runtime=rt,
                   verifier=vf.unavailable("no model configured"))
    assert rt.sent[before:] == []                    # nothing was typed at it
    assert t.state == tsk.RUNNING                    # and it is not finished


def test_an_unverified_result_is_recorded_as_unverified(config, agent):
    from ai4science.harness.agents.sarsi import ledger, verifier as vf
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.verify(config, agent, t, evidence="e", runtime=rt,
               verifier=vf.unavailable("nothing installed"))
    last = ledger.read(config, "reports")[-1]
    assert last["verdict"]["state"] == "UNVERIFIED"
    assert last["state"] == "unverified"


def test_a_real_fail_still_steers_because_someone_judged_it(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    ses.verify(config, agent, t, evidence="rows: 3", runtime=rt,
               verifier=lambda **kw: {"state": "FAIL", "why": "only 3 rows"})
    assert "only 3 rows" in rt.sent[-1][1]


def test_the_answer_says_it_could_not_be_judged(config, agent):
    from ai4science.harness.agents.sarsi import verifier as vf
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.verify(config, agent, t, evidence="e", runtime=rt,
                   verifier=vf.unavailable("no model configured"))
    answer = ses.answer(config, agent, t).lower()
    assert "not judged" in answer or "unverified" in answer
    assert not answer.startswith("verified")


def test_the_worker_cannot_pass_its_own_work(config, agent):
    """There is no path from the worker to a verdict except the verifier."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    with pytest.raises(worker.UnverifiedClaim):
        tsk.finish(config, agent, t, verdict=None)


def test_a_verdict_records_which_engine_judged_and_whether_it_was_independent(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.verify(config, agent, t, evidence="ok", engine="engine-b",
                   verifier=lambda **kw: {"state": "PASS"})
    assert t.verdict["engine"] == "engine-b"
    assert t.verdict["independent"] is True


def test_a_same_engine_verdict_says_so_rather_than_claiming_independence(config, agent):
    """A different engine is the cheapest independence available. When it is the
    same one, the verdict must not pretend otherwise."""
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.verify(config, agent, t, evidence="ok",
                   engine=t.session["engine"],
                   verifier=lambda **kw: {"state": "PASS"})
    assert t.verdict["independent"] is False


def test_the_session_records_the_engine_that_actually_ran_it(config, agent):
    """Not the worker's planning model. The worker plans with one engine and the
    session is executed by another, and independence is a claim about the one
    that did the work."""
    t = ses.assign(config, agent, _task(config, agent), runtime=FakeRuntime())
    assert t.session["engine"] == "claude"
    assert t.session["planner"] == agent.model


def test_independence_is_measured_against_the_session_not_the_planner(config, agent):
    """The live run caught this: the verifier ran `claude`, the session ran
    `claude`, and the verdict claimed independence because the worker's PLANNING
    model happened to be a different string."""
    t = ses.assign(config, agent, _task(config, agent), runtime=FakeRuntime())
    t = ses.verify(config, agent, t, evidence="ok", engine="claude",
                   verifier=lambda **kw: {"state": "PASS"})
    assert t.verdict["independent"] is False


# ── what comes back up ────────────────────────────────────────────────

def test_the_answer_states_the_authority_of_its_claim(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    t = ses.verify(config, agent, t, evidence="ok",
                   verifier=lambda **kw: {"state": "PASS"})
    assert ses.answer(config, agent, t).startswith("verified")


def test_an_unverified_task_answers_at_a_weaker_authority(config, agent):
    rt = FakeRuntime()
    t = ses.assign(config, agent, _task(config, agent), runtime=rt)
    answer = ses.answer(config, agent, t)
    assert not answer.startswith("verified")
    assert t.session["name"] in answer          # and names the session doing it
