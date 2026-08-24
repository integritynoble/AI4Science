"""The nine gaps the audit recorded open, one section each.

Each was a design decision rather than a defect: a function nobody called, a
type nobody implemented, a rule that existed as a sentence and not as code.
"""
import json
import os
import pathlib
import subprocess
import time

import pytest

from ai4science.harness.agents.machine import session as gate
from ai4science.harness.agents.sarsi import (consolidate, forecast as fc,
                                             ledger, memory, plan as pl,
                                             registry as reg, selfaware as sa,
                                             selfmodel as sm, semantic,
                                             session as ses, task as tsk,
                                             verify, worker as wk)


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
    def __init__(self): self.stopped = []
    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}
    def send(self, name, text): return {"ok": True}
    def stop(self, name): self.stopped.append(name); return {"ok": True}
    def set_ceiling(self, name, c): return {"name": name, "ceiling": c}


def _task(config, agent, criteria=("out.txt exists",), goal="produce it"):
    P = pl.Plan(goal=goal, phases=[pl.Phase(title=f"p{i}", verified_when=c)
                                   for i, c in enumerate(criteria)])
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal=goal))
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(P.render())
    return tsk.attach_plan(config, agent, t, P)


# ── 1. the four unwired M5 triggers ─────────────────────────────────────────

def test_all_eight_hard_triggers_exist(config, agent):
    assert set(memory.TRIGGERS) >= {
        "refuted_prediction", "rollback", "refusal", "clash", "correction",
        "denial", "expectation_timeout", "success"}


def test_an_admission_denial_writes_an_episode(config, agent):
    wk.admit(config, agent, wk.Directive(agent_id=agent.id, goal="do it",
                                         requires_tools=["no-such-tool-xyz"]))
    assert [e for e in ledger.read(config, "episodes")
            if e.get("trigger") == "denial"]


def test_an_expectation_that_times_out_writes_one_episode(config, agent):
    t = _task(config, agent)
    t.max_minutes = 5
    t = fc.record(config, agent, t, 0.8, why="test")
    t.forecast["at"] = time.time() - 3600
    tsk._save(agent, t)
    assert len(ses.check_expectations(config, agent)) == 1
    assert ses.check_expectations(config, agent) == []   # and not one per sweep


def test_a_verified_success_is_evidence_too(config, agent):
    t = _task(config, agent)
    wd = ses.work_dir_for(agent, t)
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "out.txt").write_text("x")
    ses.verify(config, agent, t, verifier=lambda **k: {"state": "PASS", "why": "ok"},
               evidence="e", runtime=Runtime(), now=time.time)
    eps = [e for e in ledger.read(config, "episodes") if e.get("trigger") == "success"]
    assert eps and eps[0]["outcome"] == "pass"


def test_and_a_repeated_success_can_become_a_skill_candidate(config, agent):
    """`_trigger_outcome` had no "pass", so the consolidator's success arm was
    unreachable from the live path however often a workflow worked."""
    for _ in range(3):
        t = _task(config, agent, goal="build then test then deploy")
        wd = ses.work_dir_for(agent, t)
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "out.txt").write_text("x")
        ses.verify(config, agent, t, verifier=lambda **k: {"state": "PASS", "why": "ok"},
                   evidence="e", runtime=Runtime(), now=time.time)
    assert consolidate.run(config, agent)["skill_candidates"]


# ── 2. the consolidator has a door ──────────────────────────────────────────

def test_the_consolidator_is_reachable_from_the_cli():
    from ai4science.commands import sarsi as cli
    names = {c.name for c in cli.app.registered_commands}
    assert {"consolidate", "promote", "candidates"} <= names


# ── 3. the operation-specific readiness gate is wired, and can degrade ──────

def test_assign_asks_the_operation_specific_gate(config, agent):
    import inspect
    src = inspect.getsource(ses.assign)
    assert '_sm.gate(config, agent, "assign_executor"' in src


def test_a_declared_absent_field_degrades_rather_than_blocks(config, agent,
                                                             monkeypatch):
    """`degraded_ok` could never be produced: no operation both required
    `executor_reachable` and declared itself legal without it."""
    monkeypatch.setattr(sm.shutil, "which", lambda n: None)
    got = sm.gate(config, agent, "plan_task")
    assert got.ready and got.degraded_ok
    assert any("executor_reachable" in g for g in got.gaps)
    assert not sm.gate(config, agent, "assign_executor", task=_task(config, agent)).ready


# ── 4. the three missing criterion types ────────────────────────────────────

def test_a_file_content_predicate(tmp_path):
    (tmp_path / "out.txt").write_text("the total is 111\n")
    assert verify.check("out.txt contains 111", tmp_path)["state"] == "PASS"
    assert verify.check("out.txt contains 999", tmp_path)["state"] == "FAIL"


def test_a_file_hash_predicate(tmp_path):
    import hashlib
    (tmp_path / "out.txt").write_text("x")
    h = hashlib.sha256(b"x").hexdigest()
    assert verify.check(f"sha256 of out.txt is {h[:32]}", tmp_path)["state"] == "PASS"
    assert verify.check("sha256 of out.txt is deadbeefdead", tmp_path)["state"] == "FAIL"


def test_a_json_field_predicate(tmp_path):
    (tmp_path / "m.json").write_text(json.dumps({"accuracy": 0.94, "ok": True}))
    assert verify.check("the field accuracy in m.json is at least 0.9",
                        tmp_path)["state"] == "PASS"
    assert verify.check("the field accuracy in m.json is at least 0.99",
                        tmp_path)["state"] == "FAIL"
    assert verify.check("the field ok in m.json is true", tmp_path)["state"] == "PASS"
    assert verify.check("the field nope in m.json is true", tmp_path)["state"] == "FAIL"


def test_a_diff_restricted_to_declared_paths(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x")
    assert verify.check("the diff touches only src/", tmp_path)["state"] == "PASS"
    (tmp_path / "stray.txt").write_text("x")
    assert verify.check("the diff touches only src/", tmp_path)["state"] == "FAIL"


def test_the_task_may_touch_declaration_is_finally_consulted(tmp_path):
    """`may_touch` was parsed onto the task and no check ever read it."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, capture_output=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("x")
    ok = verify.check("no files outside declared paths were modified", tmp_path,
                      may_touch=["docs/"])
    bad = verify.check("no files outside declared paths were modified", tmp_path,
                       may_touch=["src/"])
    assert ok["state"] == "PASS" and bad["state"] == "FAIL"


# ── 5. plan-time rejection, and a downgrade that says so ───────────────────

def test_an_undeterministic_criterion_is_named_at_plan_time():
    P = pl.Plan(goal="g", phases=[pl.Phase(title="a", verified_when="out.txt exists"),
                                  pl.Phase(title="b", verified_when="the code is clean")])
    weak = pl.undeterministic(P)
    assert [i for i, _, _ in weak] == [1]


def test_strict_mode_rejects_it_outright(monkeypatch):
    monkeypatch.setenv("SARSI_STRICT_CRITERIA", "1")
    P = pl.Plan(goal="g", phases=[pl.Phase(title="b", verified_when="the code is clean")])
    with pytest.raises(pl.BadPlan):
        pl.require_checkable(P)


def test_and_lenient_mode_declares_rather_than_rejects(monkeypatch):
    monkeypatch.delenv("SARSI_STRICT_CRITERIA", raising=False)
    P = pl.Plan(goal="g", phases=[pl.Phase(title="b", verified_when="the code is clean")])
    assert len(pl.require_checkable(P)) == 1


def test_a_verdict_says_whether_a_check_or_an_opinion_produced_it(config, agent):
    t = _task(config, agent, criteria=("the code is clean and well written",))
    t = ses._verify_phase(config, agent, t,
                          verifier=lambda **k: {"state": "PASS", "why": "fine"},
                          evidence="e", engine="claude", index=0, now=time.time)
    v = t.phase_verdicts["0"]
    assert v["criterion_kind"] == "judgmental" and v["deterministic"] is False


# ── 6. the verifier fingerprint, pinned and travelling ─────────────────────

def test_the_baseline_is_taken_at_import_not_at_first_use():
    assert set(ses._VERIFIER_BASELINE) == set(ses.PROTECTED_VERIFIER_MODULES)
    assert ses._check_verifier_integrity()[0] is True


def test_the_verifier_fingerprint_travels_in_the_verdict(config, agent):
    t = _task(config, agent)
    wd = ses.work_dir_for(agent, t)
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "out.txt").write_text("x")
    t = ses._verify_phase(config, agent, t, verifier=lambda **k: {"state": "FAIL"},
                          evidence="", engine="claude", index=0, now=time.time)
    assert t.phase_verdicts["0"]["verifier"] == ses.verifier_fingerprint()


# ── 7. the policy gate protects the verifier from a task session ───────────

V = "/x/ai4science/harness/agents/sarsi/verify.py"


def test_a_governed_task_session_may_not_write_the_verifier():
    for ceiling in ("A1", "A2", "A3"):
        d = gate.decide_tool_call({"tool_name": "Write",
                                   "tool_input": {"file_path": V, "content": "x"}},
                                  ceiling=ceiling, governed=True)
        assert d["decision"] == "deny", ceiling


def test_but_a_human_implementing_the_verifier_is_not_blocked():
    """§M4.2's development-time bootstrap. Blanket protection made the very
    session implementing verify.py unable to write it."""
    d = gate.decide_tool_call({"tool_name": "Write",
                               "tool_input": {"file_path": V, "content": "x"}},
                              ceiling="A1", governed=False)
    assert d["decision"] == "allow"


def test_governor_config_stays_shut_for_everyone():
    for governed in (True, False):
        d = gate.decide_tool_call(
            {"tool_name": "Write",
             "tool_input": {"file_path": "/x/.claude/settings.json", "content": "x"}},
            ceiling="A3", governed=governed)
        assert d["decision"] == "deny"


def test_a_shell_redirect_into_the_verifier_is_not_read_only():
    assert gate.classify_command(f"echo pwned > {V}", True)["kind"] == "protected"
    assert gate.classify_command("echo x > ~/.bashrc")["kind"] == "consequential"


def test_but_merely_naming_the_path_is_still_a_read():
    """The blast-radius rule: a false positive should cost one command, not a
    session — and reading about a path is not writing it."""
    assert gate.classify_command(f"grep -n check {V}", True)["kind"] == "read"


# ── 8. a real total budget, with an output reserve ─────────────────────────

def test_every_mode_stays_inside_its_total_budget(config, agent):
    from ai4science.harness.agents.sarsi import log, mode
    for i in range(400):
        log.append(agent.agent_dir, "cli", f"turn {i} " + "x" * 400, "y" * 400)
    for line in ("hello", "how does the gate compare to flat injection?",
                 "archive tsk_ab12"):
        sa.workspace_context(config, agent, observation=line, route=mode.route(line))
        row = sa.manifest(agent.agent_dir)[-1]
        lim = sa.CONTEXT_BUDGET[row["mode"]]
        assert row["token_estimate"] <= lim["total_tokens"] - lim["output_reserve"]


def test_what_was_trimmed_for_the_total_is_named(config, agent):
    from ai4science.harness.agents.sarsi import log, mode
    for i in range(400):
        log.append(agent.agent_dir, "cli", f"turn {i} " + "x" * 400, "y" * 400)
    sa.workspace_context(config, agent, observation="hello", route=mode.route("hello"))
    row = sa.manifest(agent.agent_dir)[-1]
    assert row["omitted"].get("trimmed_for_total")


def test_each_section_carries_its_own_hash(config, agent):
    from ai4science.harness.agents.sarsi import mode
    sa.workspace_context(config, agent, observation="hello", route=mode.route("hello"))
    row = sa.manifest(agent.agent_dir)[-1]
    assert all(s.get("sha256") for s in row["sections"])


def test_the_candidates_that_lost_are_named_not_just_counted(config, agent):
    from ai4science.harness.agents.sarsi import mode
    for i in range(30):
        semantic.record(config, agent, f"learned fact {i} about widgets in the field",
                        kind="lesson")
    sa.workspace_context(config, agent, observation="compare",
                         route=mode.route("how does A compare to B?"))
    row = sa.manifest(agent.agent_dir)[-1]
    assert len(row["omitted"]["semantic_candidate_ids"]) > 0


# ── 9. the delegated step is actually bounded ──────────────────────────────

def test_the_delegated_step_bound_is_read(config, agent):
    import inspect
    assert "_step_is_spent" in inspect.getsource(ses._verify_phase)


def test_the_step_is_unbounded_until_calibration_says_otherwise(config, agent):
    """The bound is what tightening BUYS. Defaulting it to 1 made the
    tightened policy the standing arrangement for every worker, and released
    the session after each phase on tasks nobody had ever scored."""
    assert fc.supervision(config, agent).max_delegated_phases is None


def test_a_session_that_spends_its_step_is_released(config, agent):
    """§M3.2's first-named lever, which was set and never read."""
    # Two scored, badly overconfident forecasts: the condition that tightens.
    for i in range(2):
        past = _task(config, agent, goal=f"earlier {i}")
        past = fc.record(config, agent, past, 0.95, why="test")
        past.verdict = {"state": "FAIL", "why": "did not work"}
        tsk._save(agent, past)
    sup = fc.supervision(config, agent)
    assert sup.level == "tighter" and sup.max_delegated_phases == 1

    t = _task(config, agent, criteria=("a.txt exists", "b.txt exists", "c.txt exists"))
    rt = Runtime()
    t = ses.assign(config, agent, t, runtime=rt, installed=lambda: set())
    wd = ses.work_dir_for(agent, t)
    wd.mkdir(parents=True, exist_ok=True)
    for f in ("a.txt", "b.txt", "c.txt"):
        (wd / f).write_text("x")
    assert t.session is not None
    t = ses._verify_phase(config, agent, t, verifier=lambda **k: {"state": "FAIL"},
                          evidence="", engine="claude", index=0, now=time.time)
    assert t.session is None, "the tightened allowance is one phase"
    assert tsk.earliest_incomplete(t) == 1


# ── the goal the plan carries is still the owner's goal ─────────────────────

def _drift_case(config, agent, goal, plan_goal, criterion, content):
    from ai4science.harness.agents.sarsi import plan as _pl
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal=goal))
    P = _pl.Plan(goal=plan_goal,
                 phases=[_pl.Phase(title="w", verified_when=criterion)])
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(P.render())
    t = tsk.attach_plan(config, agent, t, P)
    t.plan_owner_edited = True
    wd = ses.work_dir_for(agent, t)
    wd.mkdir(parents=True, exist_ok=True)
    (wd / criterion.split()[0]).write_text(content)
    t = ses._verify_phase(config, agent, t, verifier=lambda **k: {"state": "FAIL"},
                          evidence="", engine="stub", index=0, now=time.time)
    return t.phase_verdicts["0"]


def test_a_session_rewriting_the_goal_is_reported_on_the_verdict(config, agent):
    """Found by running ten real tasks. The owner asked for RESULT.txt "saying
    the run failed" against a criterion of "contains SUCCEEDED"; the session,
    given authorship of plan0.md, resolved the contradiction by rewriting the
    GOAL, wrote SUCCEEDED, and the deterministic check passed it. The task
    reached `verified` with the instruction inverted — every part working, and
    the criterion not being the point.

    `criteria_drift` guarded the criteria and nothing guarded the goal."""
    v = _drift_case(config, agent, "write RESULT.txt saying the run failed",
                    "Produce RESULT.txt in this directory reporting SUCCEEDED",
                    "RESULT.txt contains SUCCEEDED", "SUCCEEDED\n")
    assert v["state"] == "PASS"          # the criterion really was met
    assert "failed" in v["goal_drift"]   # and the verdict says what was dropped


def test_but_a_faithful_rewording_is_not_reported(config, agent):
    """`create` where the owner said `write` is the same instruction. A check
    that fires on every rephrase is one nobody reads."""
    v = _drift_case(config, agent, "write VERSION.txt containing the version 1.0.0",
                    "Create VERSION.txt in this directory containing the version string 1.0.0",
                    "VERSION.txt contains 1.0.0", "1.0.0\n")
    assert "goal_drift" not in v


def test_goal_drift_reports_and_never_adopts(config, agent):
    """Same doctrine as `criteria_drift`: the file is writable by the party
    being judged, so reconciling it is a decision, not a refresh."""
    v = _drift_case(config, agent, "write RESULT.txt saying the run failed",
                    "Produce RESULT.txt reporting SUCCEEDED",
                    "RESULT.txt contains SUCCEEDED", "SUCCEEDED\n")
    t = [x for x in tsk.all_of(config, agent) if x.id][-1]
    assert t.goal == "write RESULT.txt saying the run failed"   # unchanged
    assert v.get("goal_drift")
