"""Retry — closing the loop the verifier opens.

The verifier already produces PASS / FAIL / UNVERIFIED **with a stated reason**.
Until now a FAIL just sat on the board: the owner read the reason and typed it
back into the session by hand, which is the agent asking a human to be its
message bus.

The rules that keep retry from becoming a spend-forever loop:

  * **the reason travels.** Retrying without it re-runs the same work and gets
    the same verdict; the reason is the only new information in the system.
  * **only a judged failure retries.** UNVERIFIED means nothing was judged —
    retrying it would burn a session over a *looking* problem, not a doing one.
    PASS is done.
  * **attempts are counted and capped.** After the cap it reports rather than
    spends, and says how many it used.
  * **the owner's edits survive it.** Retry is not a re-plan.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             retry as rty, session as ses,
                                             task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path / "cp"))
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
        self.started, self.sent, self.stopped = [], [], []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
        self.started.append(name)
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def stop(self, name):
        self.stopped.append(name)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _running(config, agent, rt, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t = tsk.start(config, agent, t)
    t.plan_agreed = True
    return ses.assign(config, agent, t, runtime=rt)


def _judged(t, verdict, reason):
    t.verdict = {"verdict": verdict, "reason": reason}
    return t


# ── the reason travels ────────────────────────────────────────────────

def test_retry_sends_the_verdicts_reason_into_the_session(config, agent):
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL",
                "export.csv has 0 rows, not 1204")
    rty.retry(config, agent, t, runtime=rt)
    assert "export.csv has 0 rows, not 1204" in rt.sent[-1]


def test_the_instruction_says_it_is_the_verifier_speaking(config, agent):
    """So the session does not read it as the owner changing their mind."""
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL", "the file is empty")
    rty.retry(config, agent, t, runtime=rt)
    assert "verifier" in rt.sent[-1].lower()


def test_retry_does_not_restate_the_verdict_as_a_new_goal(config, agent):
    """The goal is unchanged; only the evidence about it is new."""
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL", "the file is empty")
    after = rty.retry(config, agent, t, runtime=rt)
    assert after.goal == "finish the export"


# ── only a judged failure retries ─────────────────────────────────────

def test_a_pass_is_not_retried(config, agent):
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "PASS", "all 1204 rows present")
    with pytest.raises(rty.NothingToRetry):
        rty.retry(config, agent, t, runtime=rt)


def test_an_unverified_task_is_not_retried(config, agent):
    """Nothing was judged. Retrying spends a session on a looking problem."""
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "UNVERIFIED",
                "nothing visible was supplied")
    with pytest.raises(rty.NothingToRetry, match="nothing was judged"):
        rty.retry(config, agent, t, runtime=rt)


def test_a_task_never_judged_at_all_is_not_retried(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    with pytest.raises(rty.NothingToRetry):
        rty.retry(config, agent, t, runtime=rt)


# ── attempts are counted and capped ───────────────────────────────────

def test_each_retry_is_counted(config, agent):
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL", "still empty")
    t = rty.retry(config, agent, t, runtime=rt)
    assert t.retries == 1
    t = _judged(t, "FAIL", "still empty")
    t = rty.retry(config, agent, t, runtime=rt)
    assert t.retries == 2


def test_it_stops_at_the_cap_and_says_how_many_it_used(config, agent):
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL", "still empty")
    for _ in range(rty.MAX_RETRIES):
        t = _judged(rty.retry(config, agent, t, runtime=rt), "FAIL", "still empty")
    with pytest.raises(rty.Exhausted, match=str(rty.MAX_RETRIES)):
        rty.retry(config, agent, t, runtime=rt)


def test_the_cap_reports_rather_than_spending(config, agent):
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL", "still empty")
    for _ in range(rty.MAX_RETRIES):
        t = _judged(rty.retry(config, agent, t, runtime=rt), "FAIL", "still empty")
    before = len(rt.sent)
    with pytest.raises(rty.Exhausted):
        rty.retry(config, agent, t, runtime=rt)
    assert len(rt.sent) == before


def test_a_pass_clears_the_count(config, agent):
    """A run that succeeded should not carry its earlier failures forward."""
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL", "still empty")
    t = rty.retry(config, agent, t, runtime=rt)
    t = tsk.finish(config, agent, _judged(t, "PASS", "1204 rows"),
                   verdict={"verdict": "PASS", "reason": "1204 rows"})
    assert tsk.get(config, agent, t.id).retries == 0


# ── it is not a re-plan ───────────────────────────────────────────────

def test_the_owners_edited_criteria_survive_a_retry(config, agent):
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    t.criteria = ["the queue is empty in the console"]
    t.plan_owner_edited = True
    t = rty.retry(config, agent, _judged(t, "FAIL", "queue still at 40"),
                  runtime=rt)
    after = tsk.get(config, agent, t.id)
    assert after.criteria == ["the queue is empty in the console"]
    assert after.plan_owner_edited is True


def test_retrying_a_task_with_no_session_starts_one(config, agent):
    """A FAIL usually arrives after the session has been released."""
    rt = FakeRuntime()
    t = _judged(_running(config, agent, rt), "FAIL", "the file is empty")
    t.session = None
    t = rty.retry(config, agent, t, runtime=rt)
    assert t.session is not None
    assert len(rt.started) == 2


# ── the verdict as the SYSTEM writes it, not as this test imagines it ──

def test_retry_reads_a_verdict_in_the_shape_the_verifier_actually_writes(
        config, agent):
    """The record uses `state` / `why`. A retry keyed on `verdict` / `reason`
    would never fire on a real FAIL — it would report 'no verdict' about a task
    the verifier had just failed, and the loop would silently never close."""
    from ai4science.harness.agents.sarsi import verifier as vf
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    t.verdict = vf.parse("FAIL: export.csv has 0 rows, not 1204")
    assert set(t.verdict) == {"state", "why"}          # the real shape
    t = rty.retry(config, agent, t, runtime=rt)
    assert "export.csv has 0 rows" in rt.sent[-1]
    assert t.retries == 1


def test_a_real_pass_is_not_retried(config, agent):
    from ai4science.harness.agents.sarsi import verifier as vf
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    t.verdict = vf.parse("PASS: all 1204 rows present")
    with pytest.raises(rty.NothingToRetry):
        rty.retry(config, agent, t, runtime=rt)


def test_a_real_unverified_is_not_retried(config, agent):
    from ai4science.harness.agents.sarsi import verifier as vf
    rt = FakeRuntime()
    t = _running(config, agent, rt)
    t.verdict = vf._unverified("nothing visible was supplied")
    with pytest.raises(rty.NothingToRetry, match="nothing was judged"):
        rty.retry(config, agent, t, runtime=rt)
