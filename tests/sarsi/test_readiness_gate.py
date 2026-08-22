"""Readiness is asked per operation, and never guessed. [plan v3 §7.3, §11.5]

"Am I ready?" has no single answer. Archiving a task does not care whether a
coding binary is on PATH; assigning one does. A single global health check
either blocks work that needed none of the missing state, or waves through work
that needed all of it.

The rule these tests exist to hold: **retry exhaustion never becomes a value.**
A field that could not be observed stays unmeasured and the operation is
refused or degraded — it is not run against a number nobody measured.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             selfmodel as sm, task as tsk,
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
    return config.agents["sarsi-worker"]


def _plan():
    return pl.Plan(goal="finish the export",
                   phases=[pl.Phase(title="drain the queue",
                                    verified_when="the queue length reads 0")])


def _task(config, agent, *, with_plan=True):
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.create(config, agent, d)
    return tsk.attach_plan(config, agent, t, _plan()) if with_plan else t


# ── the requirement is per operation ─────────────────────────────────────────

def test_an_operation_that_does_not_need_a_field_is_not_blocked_by_it(config, agent,
                                                                      monkeypatch):
    """No executor on PATH must not stop a semantic write, which needs none."""
    monkeypatch.setattr(sm.shutil, "which", lambda n: None)
    got = sm.gate(config, agent, "write_semantic_memory",
                  context={"provenance": "owner said so", "scope": ["global"]})
    assert got.ready
    assert got.gaps == []


def test_the_same_missing_field_does_block_the_operation_that_needs_it(config, agent,
                                                                      monkeypatch):
    monkeypatch.setattr(sm.shutil, "which", lambda n: None)
    t = _task(config, agent)
    got = sm.gate(config, agent, "assign_executor", task=t)
    assert not got.ready
    assert any("executor_reachable" in g for g in got.gaps)


def test_a_field_declared_absent_for_this_operation_degrades_rather_than_blocks(
        config, agent, monkeypatch):
    """`MAY_BE_ABSENT` names the operations that stay legal without a field —
    in advance, in a table, rather than as an excuse after a failure."""
    monkeypatch.setattr(sm.shutil, "which", lambda n: None)
    t = _task(config, agent)
    t.verdict = {"state": "PASS"}
    got = sm.gate(config, agent, "archive_task", task=t)
    assert got.ready
    assert got.gaps == []          # archive_task never required an executor


def test_an_operation_the_gate_does_not_know_is_not_one_it_clears(config, agent):
    got = sm.gate(config, agent, "launch_the_missiles")
    assert not got.ready
    assert "declares no required state" in got.gaps[0]


# ── bounded refresh ──────────────────────────────────────────────────────────

def test_a_stale_required_field_triggers_a_bounded_refresh(config, agent, monkeypatch):
    """`authority` unmeasured: the declared observation path is `sync()`, and
    it is called — but a bounded number of times."""
    calls = []
    real_sync = sm.sync
    monkeypatch.setattr(sm, "sync", lambda c, a: calls.append(1) or real_sync(c, a))
    t = _task(config, agent)
    got = sm.gate(config, agent, "assign_executor", task=t, attempts=2)
    assert calls, "the declared refresh path was never attempted"
    assert len(calls) <= 2
    authority = [f for f in got.fields if f.name == "authority"][0]
    assert authority.validity == "fresh"       # the refresh worked


def test_an_unreachable_field_does_not_loop_forever(config, agent, monkeypatch):
    """A refresh that never fixes anything must still stop."""
    calls = []
    monkeypatch.setattr(sm, "sync", lambda c, a: calls.append(1) or [])
    t = _task(config, agent)
    got = sm.gate(config, agent, "assign_executor", task=t, attempts=3)
    assert len(calls) == 3
    assert "authority" in got.exhausted


def test_exhausted_refresh_stays_unmeasured_rather_than_becoming_a_value(
        config, agent, monkeypatch):
    monkeypatch.setattr(sm, "sync", lambda c, a: [])
    t = _task(config, agent)
    got = sm.gate(config, agent, "assign_executor", task=t, attempts=2)
    authority = [f for f in got.fields if f.name == "authority"][0]
    assert authority.validity in ("unmeasured", "stale")
    assert authority.value is None
    assert not got.ready


def test_a_task_with_no_plan_is_not_ready_to_be_assigned(config, agent):
    t = _task(config, agent, with_plan=False)
    got = sm.gate(config, agent, "assign_executor", task=t)
    assert not got.ready
    assert any("active_plan" in g for g in got.gaps)


def test_archiving_unjudged_work_is_refused(config, agent):
    """Nothing has judged it — archiving would file work no verifier saw."""
    t = _task(config, agent)
    got = sm.gate(config, agent, "archive_task", task=t)
    assert not got.ready
    assert any("verification_state" in g for g in got.gaps)


def test_a_semantic_write_without_provenance_or_scope_is_refused(config, agent):
    got = sm.gate(config, agent, "write_semantic_memory", context={})
    assert not got.ready
    assert {"provenance", "scope"} <= {f.name for f in got.fields}


def test_the_readiness_answer_is_recordable(config, agent):
    t = _task(config, agent)
    rec = sm.gate(config, agent, "archive_task", task=t).as_record()
    assert rec["operation"] == "archive_task"
    assert [f["name"] for f in rec["fields"]] == ["active_plan", "verification_state"]
