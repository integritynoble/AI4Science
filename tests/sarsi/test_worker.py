"""The worker plane: a typed directive down, an admission decision, a typed
report up.

Slice 2's observation: **a directive requiring an absent tool is refused with
what is missing named, and is not queued.** An unplaceable directive that waits
is indistinguishable, from the chat, from work in progress.
"""
import pytest

from ai4science.harness.agents.sarsi import ledger, registry as reg, worker


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


def _which(present):
    return lambda name: f"/usr/bin/{name}" if name in present else None


def _directive(**kw):
    base = dict(agent_id="work", goal="triage the mailbox and draft replies")
    base.update(kw)
    return worker.Directive(**base)


# ── DIR: the directive is a contract, not a conversation ──────────────

def test_a_directive_needs_a_goal(config):
    with pytest.raises(worker.BadDirective, match="goal"):
        _directive(goal="   ")


def test_a_directive_refuses_to_carry_the_conversation(config):
    """What crosses is what the worker needs, never the transcript of how it was
    asked — that is what keeps the session's context bounded."""
    with pytest.raises(worker.BadDirective, match="goal"):
        _directive(goal="x" * (worker.MAX_GOAL_CHARS + 1))


def test_a_directive_records_what_it_will_need(config):
    d = _directive(requires_tools=["matlab"], requires_secrets=["mail.read"])
    assert d.requires_tools == ["matlab"] and d.requires_secrets == ["mail.read"]


# ── WK: the worker admits it, or does not ─────────────────────────────

def test_a_directive_whose_tools_are_here_is_admitted(config):
    out = worker.admit(config, config.agents["work"],
                       _directive(requires_tools=["matlab"]),
                       which=_which({"matlab"}))
    assert out.admitted is True and out.missing == []


def test_a_directive_needing_an_absent_tool_is_refused(config):
    out = worker.admit(config, config.agents["work"],
                       _directive(requires_tools=["matlab"]),
                       which=_which(set()))
    assert out.admitted is False and out.reason == "capability"


def test_the_refusal_names_what_is_missing(config):
    out = worker.admit(config, config.agents["work"],
                       _directive(requires_tools=["matlab", "qupath"]),
                       which=_which({"qupath"}))
    assert out.missing == ["matlab"]
    assert "matlab" in out.message


def test_a_refused_directive_is_not_queued(config):
    """The whole point of NOM: nothing waits quietly."""
    worker.admit(config, config.agents["work"], _directive(requires_tools=["matlab"]),
                 which=_which(set()))
    assert worker.outstanding(config, config.agents["work"]) == []


def test_an_admitted_directive_is_outstanding_until_reported(config):
    agent = config.agents["work"]
    out = worker.admit(config, agent, _directive(requires_tools=["matlab"]),
                       which=_which({"matlab"}))
    assert [d["id"] for d in worker.outstanding(config, agent)] == [out.directive.id]
    worker.report(config, agent, out.directive, state="done", evidence=["did it"])
    assert worker.outstanding(config, agent) == []


# ── who may be a worker at all ────────────────────────────────────────

def test_the_manager_may_not_admit_a_directive(config):
    """§1: the agent you talk to does not execute."""
    with pytest.raises(worker.NotAWorker):
        worker.admit(config, config.agents["sarsi-machine"],
                     _directive(agent_id="sarsi-machine"), which=_which(set()))


def test_a_worker_refuses_a_directive_addressed_to_another_agent(config):
    out = worker.admit(config, config.agents["abraham"],
                       _directive(agent_id="work"), which=_which(set()))
    assert out.admitted is False and out.reason == "not-mine"


# ── REP: the report says what happened, and no more ───────────────────

def test_every_directive_is_recorded_admitted_or_not(config):
    agent = config.agents["work"]
    worker.admit(config, agent, _directive(requires_tools=["matlab"]), which=_which(set()))
    worker.admit(config, agent, _directive(requires_tools=["matlab"]),
                 which=_which({"matlab"}))
    assert ledger.count(config, "directives") == 2
    assert ledger.count(config, "directives", admitted=False) == 1


def test_a_report_is_recorded(config):
    agent = config.agents["work"]
    out = worker.admit(config, agent, _directive(), which=_which(set()))
    worker.report(config, agent, out.directive, state="done", evidence=["ran it"])
    assert ledger.count(config, "reports", agent="work", state="done") == 1


def test_a_report_may_not_claim_a_verdict_the_verifier_did_not_give(config):
    agent = config.agents["work"]
    out = worker.admit(config, agent, _directive(), which=_which(set()))
    with pytest.raises(worker.UnverifiedClaim):
        worker.report(config, agent, out.directive, state="verified", evidence=["trust me"])


def test_a_report_with_a_verdict_is_allowed(config):
    agent = config.agents["work"]
    out = worker.admit(config, agent, _directive(), which=_which(set()))
    rec = worker.report(config, agent, out.directive, state="verified",
                        evidence=["screenshot"], verdict={"state": "PASS", "by": "verifier"})
    assert rec["state"] == "verified"


def test_a_report_carrying_a_secret_is_refused(config):
    agent = config.agents["work"]
    out = worker.admit(config, agent, _directive(), which=_which(set()))
    with pytest.raises(ledger.SecretInLedger):
        worker.report(config, agent, out.directive, state="done",
                      evidence=["logged in"], extra={"password": "hunter2"})


def test_a_report_says_what_it_needed_and_did_not_get(config):
    agent = config.agents["work"]
    out = worker.admit(config, agent, _directive(requires_tools=["matlab"]),
                       which=_which(set()))
    reports = ledger.read(config, "reports")
    assert reports[-1]["needed_and_missing"] == ["matlab"]


def test_a_refusal_reports_itself_without_being_asked(config):
    """CAP → REP is automatic: the miss becomes an answer, not a silence."""
    agent = config.agents["work"]
    worker.admit(config, agent, _directive(requires_tools=["matlab"]), which=_which(set()))
    assert ledger.count(config, "reports", state="blocked") == 1
