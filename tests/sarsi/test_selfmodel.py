"""The self-model: `SA = ⟨Content, Operations, Evidence⟩`.

The agent maintains a model of what it is, what it can do, and how it knows —
where **every claim is backed by an observation**. Not a claim of consciousness.

The rules are all about honesty:
  * every line is *observed*, never asserted;
  * `s_C` counts **verified** outcomes only — what the agent claimed does not
    enter it;
  * the limits line is always present;
  * it never reports an ability it has not measured, and never self-promotes;
  * the manager's model says what it structurally cannot do.
"""
import pytest

from ai4science.harness.agents.sarsi import (outward, plan as pl, registry as reg,
                                             selfmodel as sm, task as tsk,
                                             vault, worker)


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
    return pl.Plan(goal="g", phases=[pl.Phase(title="p", verified_when="v")])


def _task(config, agent, goal="a job"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    return tsk.attach_plan(config, agent, tsk.create(config, agent, d), _plan())


def _field(claims, name):
    return next((c for c in claims if c.field == name), None)


# ── every claim carries its source ────────────────────────────────────

def test_every_claim_names_where_it_came_from(config, agent):
    for claim in sm.model(config, agent):
        assert claim.source, f"{claim.field} has no source"


def test_no_claim_is_merely_asserted(config, agent):
    """A self-model line without an observation behind it is a boast."""
    for claim in sm.model(config, agent):
        assert claim.source not in ("assumed", "", None)


def test_the_limits_line_is_always_present(config, agent):
    text = sm.render(config, agent)
    assert "unverified" in text.lower()


def test_it_does_not_claim_an_ability_it_has_not_measured(config, agent):
    """Asked about something nothing probes, it says so rather than inventing."""
    assert sm.competence(config, agent, "poetry") == "unverified"


# ── the counts are real ───────────────────────────────────────────────

def test_tasks_held_matches_the_task_records(config, agent):
    _task(config, agent, "one")
    _task(config, agent, "two")
    assert _field(sm.model(config, agent), "tasks_held").value == 2


def test_verified_counts_only_what_the_verifier_granted(config, agent):
    """s_C is written by the verifier, never by the agent."""
    done = tsk.start(config, agent, _task(config, agent, "one"))
    tsk.finish(config, agent, done, verdict={"state": "PASS", "by": "verifier"})
    tsk.start(config, agent, _task(config, agent, "two"))     # running, unverified
    assert _field(sm.model(config, agent), "verified").value == 1


def test_an_unverified_success_never_enters_the_record(config, agent):
    t = tsk.start(config, agent, _task(config, agent))
    t.state = "running"
    assert _field(sm.model(config, agent), "verified").value == 0


def test_vault_counts_come_from_the_vault_ledger(config, agent):
    vault.put(config, "mail.read", "x")
    vault.ask(config, agent_id="work", secret="mail.read", act="read",
              purpose="p", prompt=lambda **kw: "yes")
    vault.ask(config, agent_id="work", secret="mail.read", act="read",
              purpose="p", prompt=lambda **kw: "no")
    claim = _field(sm.model(config, agent), "vault")
    assert claim.value == {"asked": 2, "allowed": 1, "denied": 1}


def test_outward_counts_come_from_the_outward_ledger(config, agent):
    act = outward.Act(agent_id="work", kind="mail", destination="d", body="b")
    outward.request(config, agent, act, approve=lambda **kw: "no",
                    transmit=lambda a, *, body: body)
    claim = _field(sm.model(config, agent), "outward")
    assert claim.value["refused"] == 1 and claim.value["sent"] == 0


def test_the_playbook_version_is_reported_from_disk(config, agent):
    from ai4science.harness.agents.sarsi import playbook as pb
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 4})
    pb.sign(config, agent, by_owner=True)
    assert _field(sm.model(config, agent), "playbook").value["version"] == 2


# ── engines ───────────────────────────────────────────────────────────

def test_engines_are_probed_not_declared(config, agent):
    claim = _field(sm.model(config, agent), "engines")
    assert "probe" in claim.source.lower() or "path" in claim.source.lower()


# ── the manager knows what it cannot do ───────────────────────────────

def test_the_manager_reports_that_it_cannot_drive_a_session(config):
    text = sm.render(config, config.agents["sarsi-machine"])
    assert "cannot" in text.lower() and "session" in text.lower()


def test_the_manager_holds_no_tasks_and_says_so(config):
    claim = _field(sm.model(config, config.agents["sarsi-machine"]), "tasks_held")
    assert claim.value == 0


def test_a_worker_does_not_claim_the_managers_line(config, agent):
    assert "I route" not in sm.render(config, agent)


# ── isolation ─────────────────────────────────────────────────────────

def test_one_agents_model_does_not_count_anothers_work(config, config_other=None):
    _task(config, config.agents["work"], "work's job")
    assert _field(sm.model(config, config.agents["abraham"]), "tasks_held").value == 0


# ── it never promotes itself ──────────────────────────────────────────

def test_the_model_reports_a_pending_candidate_without_adopting_it(config, agent):
    from ai4science.harness.agents.sarsi import playbook as pb
    pb.propose(config, agent, evidence={"blocked_by_concurrency": 4})
    text = sm.render(config, agent)
    assert "awaiting your signature" in text.lower()
    assert pb.read(config, agent)["version"] == 1
