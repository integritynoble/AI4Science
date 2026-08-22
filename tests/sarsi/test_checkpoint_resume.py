"""Picking the plan back up after a restart. [plan v3 §M3.3, §11.6]

Three ways this goes wrong quietly, one test family each:

  * a checkpoint half-written by a process that died mid-write is a confident
    record of a state that never existed;
  * `plan0` after the owner rewrote its criteria is a different plan wearing
    the same name, and resuming "phase 3" of it is the silent version of doing
    the wrong work;
  * a checkpoint that records `passed: [0, 1]` without the verdicts repeats a
    claim without its grounds.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (checkpoint as ck, plan as pl,
                                             registry as reg, task as tsk,
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
                                    verified_when="the queue length reads 0"),
                           pl.Phase(title="re-run the export",
                                    verified_when="export.csv has 1,204 rows"),
                           pl.Phase(title="publish it",
                                    verified_when="the published hash matches")])


def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    return tsk.attach_plan(config, agent, tsk.create(config, agent, d), _plan())


def _pass(config, agent, t, i):
    return tsk.record_phase(config, agent, t, i,
                            {"state": "PASS", "why": f"phase {i} checked",
                             "engine": "deterministic", "independent": True})


# ── the write ────────────────────────────────────────────────────────────────

def test_the_checkpoint_records_what_is_verified_and_what_is_next(config, agent):
    t = _pass(config, agent, _task(config, agent), 0)
    got = ck.write(config, agent, t)
    assert got.phases_verified == [0]
    assert got.current_phase == 1


def test_each_verified_phase_carries_the_evidence_that_verified_it(config, agent):
    t = _pass(config, agent, _task(config, agent), 0)
    ck.write(config, agent, t)
    back = ck.read(agent, t.id)
    assert back.evidence["0"]["state"] == "PASS"
    assert back.evidence["0"]["engine"] == "deterministic"
    assert back.evidence["0"]["independent"] is True


def test_the_write_is_atomic_and_leaves_no_temporary_behind(config, agent):
    t = _pass(config, agent, _task(config, agent), 0)
    ck.write(config, agent, t)
    d = tsk.dir_of(agent, t.id)
    assert (d / "checkpoint.json").exists()
    assert not list(d.glob("*.tmp"))
    json.loads((d / "checkpoint.json").read_text())     # complete, not partial


# ── the resume ───────────────────────────────────────────────────────────────

def test_a_restart_resumes_the_first_unverified_phase(config, agent):
    t = _task(config, agent)
    t = _pass(config, agent, t, 0)
    t = _pass(config, agent, t, 1)
    ck.write(config, agent, t)
    got = ck.resume_point(config, agent, t)
    assert got.ok and got.phase == 2


def test_with_no_checkpoint_it_falls_back_to_the_task_store_and_says_so(config, agent):
    t = _pass(config, agent, _task(config, agent), 0)
    got = ck.resume_point(config, agent, t)
    assert got.ok and got.phase == 1
    assert "no checkpoint" in got.why


def test_a_changed_plan_does_not_resume_blindly(config, agent):
    """The owner rewrote the criteria. Phase 2 is no longer phase 2."""
    t = _pass(config, agent, _task(config, agent), 0)
    ck.write(config, agent, t)
    t.criteria = ["something else entirely", "and another thing"]
    got = ck.resume_point(config, agent, t)
    assert not got.ok
    assert got.blocked == ck.REBASE
    assert got.phase is None
    assert "changed under this checkpoint" in got.why


def test_a_rename_alone_is_not_a_change_of_work(config, agent):
    """The hash covers the goal and the criteria, not the plan's name."""
    t = _pass(config, agent, _task(config, agent), 0)
    ck.write(config, agent, t)
    t.plan_version = "plan1"
    got = ck.resume_point(config, agent, t)
    assert got.ok and got.phase == 1


def test_an_old_checkpoint_without_a_hash_is_used_and_called_weaker(config, agent):
    t = _pass(config, agent, _task(config, agent), 0)
    d = tsk.dir_of(agent, t.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "checkpoint.json").write_text(json.dumps(
        {"task_id": t.id, "plan_version": "plan0", "current_phase": 1,
         "phases_verified": [0], "last_updated": "2026-08-21T00:00:00+00:00"}))
    got = ck.resume_point(config, agent, t)
    assert got.ok and got.phase == 1
    assert "predates plan hashing" in got.why


def test_the_session_writes_the_checkpoint_through_the_same_path(config, agent):
    """`_verify_phase` must not keep its own private writer — one home."""
    import inspect

    from ai4science.harness.agents.sarsi import session as ses
    src = inspect.getsource(ses._verify_phase)
    assert "checkpoint as _ck" in src
    assert "write_text" not in src.split("checkpoint")[1][:400]
