"""Defects found by a live audit of the plan, one test each.

Every one of these was invisible to a green suite: the code did what it was
written to do, and what it was written to do was wrong in a way only a live
run — or a reader with the spec open beside them — could see.
"""
import os
import pathlib
import tempfile
import time

import pytest

from ai4science.harness.agents.sarsi import (checkpoint as ck, consolidate,
                                             forecast as fc, ledger, memory,
                                             mode, plan as pl, registry as reg,
                                             selfaware as sa, semantic,
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
    def __init__(self): self.sent, self.stopped = [], []
    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}
    def send(self, name, text): self.sent.append((name, text)); return {"ok": True}
    def stop(self, name): self.stopped.append(name); return {"ok": True}
    def set_ceiling(self, name, c): return {"name": name, "ceiling": c}


def _task(config, agent, criteria=("out.txt exists",), goal="produce it"):
    P = pl.Plan(goal=goal, phases=[pl.Phase(title=f"p{i}", verified_when=c)
                                   for i, c in enumerate(criteria)])
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal=goal))
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(P.render())
    return tsk.attach_plan(config, agent, t, P)


# ── the ledger's promise, actually kept ──────────────────────────────────────

def test_a_credential_in_free_text_does_not_reach_a_ledger(config, agent):
    """The filter looked at top-level KEYS only, and the semantic channel's
    payload is a free-text statement that `render()` puts into the model's
    context. "no secret ever enters a ledger" was a claim, not a check."""
    for bad in ("the deploy api_key is sk-live-ABCDEF123456",
                "password: hunter2trombone",
                "-----BEGIN RSA PRIVATE KEY-----",
                "AKIAIOSFODNN7EXAMPLE is set in the env"):
        with pytest.raises(ledger.SecretInLedger):
            semantic.record(config, agent, bad, kind="lesson")


def test_but_naming_which_secret_is_involved_stays_legal(config, agent):
    """The vault has to record WHICH secret was asked for. A filter that
    refuses that deletes the record it exists to keep."""
    semantic.record(config, agent, "the mail.read secret is needed for this task")
    semantic.record(config, agent, "the password prompt appeared and it stalled")
    ledger.append(config, "vault", {"agent": agent.id, "secret_name": "mail.read",
                                    "decision": "ALLOW"})


def test_a_refused_episode_does_not_come_back_looking_written(config, agent):
    with pytest.raises(ledger.SecretInLedger):
        memory.record_episode(config, agent, trigger="refusal",
                              summary="token=ghp_ABCDEFG1234567890XYZ")
    assert [r for r in ledger.read(config, "episodes")] == []


# ── promotion is a decision, and it happens once ─────────────────────────────

def test_a_candidate_cannot_be_promoted_twice(config, agent):
    rec = semantic.record(config, agent, "flaky test X needs a retry",
                          status="candidate", provenance=["ep_1"])
    semantic.promote(config, agent, rec["memory_id"])
    with pytest.raises(semantic.PromotionBlocked):
        semantic.promote(config, agent, rec["memory_id"])
    assert len([e for e in semantic.active_entries(config, agent)
                if "flaky test X" in e["statement"]]) == 1


def test_a_promoted_candidate_stops_being_offered(config, agent):
    rec = semantic.record(config, agent, "a thing", status="candidate")
    assert [c["memory_id"] for c in semantic.candidates(config, agent)] == [rec["memory_id"]]
    semantic.promote(config, agent, rec["memory_id"])
    assert semantic.candidates(config, agent) == []


def test_an_entry_can_be_retracted_without_inventing_a_replacement(config, agent):
    rec = semantic.record(config, agent, "the exporter writes CSV only",
                          kind="invariant")
    semantic.retract(config, agent, rec["memory_id"], reason="no longer true")
    assert rec["memory_id"] not in {e["memory_id"]
                                    for e in semantic.active_entries(config, agent)}


# ── directives: a revoke names something, a supersede names its replacement ──

def test_revoking_a_directive_that_does_not_exist_is_refused(config, agent):
    with pytest.raises(wk.UnknownDirective):
        wk.revoke(config, agent, "dir_never_issued")


def test_a_supersede_says_what_replaced_it(config, agent):
    got = wk.admit(config, agent, wk.Directive(agent_id=agent.id, goal="first"))
    old_id = [d["id"] for d in wk.outstanding(config, agent)][0]
    wk.supersede_directive(config, agent, old_id,
                           wk.Directive(agent_id=agent.id, goal="second"))
    events = [r for r in ledger.read(config, "directives")
              if r.get("op") == "supersede"]
    assert events and events[-1].get("superseded_by")


# ── the gate: a constraint is never the thing that gets dropped ──────────────

def test_a_constraint_written_last_is_still_in_an_action_context(config, agent):
    """Insertion-order truncation meant an owner constraint written after
    sixty lessons was silently absent from the context of a consequential
    turn — the one failure the protected section exists to prevent."""
    for i in range(60):
        semantic.record(config, agent,
                        f"learned lesson {i} about widgets and their behaviours",
                        kind="lesson")
    semantic.record(config, agent, "never write to /prod without an owner grant",
                    kind="invariant", scope=["global"])
    text, report = semantic.render_parts(config, agent)
    assert "/prod" in text
    assert report["protected_dropped"] == 0
    assert report["omitted"] > 0            # and the omission is counted


def test_an_action_turn_fails_closed_when_constraints_do_not_fit(config, agent):
    """§7.2: for a consequential turn, constraints that do not fit are not
    silently omitted — the turn stops."""
    for i in range(200):
        semantic.record(config, agent,
                        f"never do the forbidden thing number {i} under any "
                        f"circumstances whatsoever, ever",
                        kind="invariant", scope=["global"])
    with pytest.raises(sa.ProtectedOverflow):
        sa.workspace_context(config, agent, observation="drop the stale tables",
                             route=mode.route("archive tsk_ab12"))


def test_a_relevant_older_episode_is_not_crowded_out_by_recent_noise(config, agent):
    """§11.3(c). The recency anchor spent the whole episodic budget, so once
    three chatty recent turns exceeded the cap nothing scored could be
    admitted — the subtle failure, and the one that matters."""
    from ai4science.harness.agents.sarsi import log
    log.append(agent.agent_dir, "cli",
               "the mask calibration for CASSI must use the continuous mask",
               "noted", task_id="tsk_rel")
    for i in range(3):
        log.append(agent.agent_dir, "cli", "x" * 600 + f" recent {i}", "y" * 600)
    ctx = sa.workspace_context(
        config, agent, observation="what about the CASSI mask calibration?",
        route=mode.route("what about the CASSI mask calibration?"))
    assert "continuous mask" in ctx


def test_the_manifest_records_real_semantic_ids(config, agent):
    """They were all empty strings: the field is `memory_id`, not `id`."""
    semantic.record(config, agent, "prefer the continuous mask",
                    kind="invariant", scope=["global"])
    sa.workspace_context(config, agent, observation="mask?",
                         route=mode.route("how does the mask compare to the alternative?"))
    row = sa.manifest(agent.agent_dir)[-1]
    assert row["selected"]["semantic"] and all(row["selected"]["semantic"])


def test_a_broken_store_is_visible_in_the_manifest(config, agent, monkeypatch):
    """§11.3(e). `retrieve()` swallows store failures, so a turn that lost
    every constraint looked identical to a turn that had none."""
    from ai4science.harness.agents.sarsi import semantic as _sem
    monkeypatch.setattr(_sem, "active_entries",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("index gone")))
    sa.workspace_context(config, agent, observation="compare the approaches",
                         route=mode.route("how does the gate compare to flat injection?"))
    row = sa.manifest(agent.agent_dir)[-1]
    assert "retrieval failed" in str(row["omitted"].get("semantic", ""))


# ── the verifier: the judged party does not choose its judge ─────────────────

def test_an_unagreed_criterion_cannot_make_the_worker_run_a_command(tmp_path):
    """The executor writes plan0.md; its `Verified when:` lines become the
    criteria verbatim. This used to shlex-split the backticks and run them."""
    marker = tmp_path / "should-not-exist"
    got = verify.check(f"`/bin/touch {marker}` exits 0", tmp_path, trusted=False)
    assert got["state"] == "UNVERIFIED"
    assert not marker.exists()


def test_a_recognised_check_still_runs_from_an_unagreed_plan(tmp_path):
    """The allowlist keeps ordinary verification working — the gate opens."""
    assert verify._is_safe_command("pytest -x")
    assert verify._is_safe_command("git status --porcelain")
    assert not verify._is_safe_command("cat /etc/passwd")
    assert not verify._is_safe_command("bash -c 'rm -rf /'")


def test_an_owner_agreed_criterion_may_name_a_command(tmp_path):
    got = verify.check("`/bin/true` exits 0", tmp_path, trusted=True)
    assert got["state"] == "PASS"


def test_a_sibling_directory_is_not_inside_the_work_dir(tmp_path):
    """`/base/work-evil` string-starts-with `/base/work`."""
    work = tmp_path / "work"
    work.mkdir()
    evil = tmp_path / "work-evil"
    evil.mkdir()
    (evil / "loot.txt").write_text("loot")
    got = verify.check("../work-evil/loot.txt exists", work)
    assert got["state"] == "UNVERIFIED"


def test_a_criterion_with_two_clauses_is_judged_on_both(tmp_path):
    (tmp_path / "report.md").write_text("x")
    bad = verify.check("report.md exists and `/bin/false` exits 0", tmp_path,
                       trusted=True)
    good = verify.check("report.md exists and `/bin/true` exits 0", tmp_path,
                        trusted=True)
    assert bad["state"] == "FAIL"
    assert good["state"] == "PASS"


def test_an_expected_nonzero_exit_code_is_honoured(tmp_path):
    assert verify.check("`/bin/false` exits with code 1", tmp_path,
                        trusted=True)["state"] == "PASS"


def test_an_output_criterion_is_not_downgraded_to_an_exit_check(tmp_path):
    """It passed on exit 0 while the output plainly lacked the string."""
    (tmp_path / "out.txt").write_text("hello world\n")
    assert verify.check("output of `cat out.txt` contains ZZZNOTHERE", tmp_path,
                        trusted=True)["state"] == "FAIL"
    assert verify.check("output of `cat out.txt` contains hello", tmp_path,
                        trusted=True)["state"] == "PASS"


def test_a_bare_command_with_no_stated_expectation_is_not_a_pass(tmp_path):
    assert verify.check("`/bin/true`", tmp_path, trusted=True)["state"] == "UNVERIFIED"


# ── the checkpoint: durable, or loud ────────────────────────────────────────

def test_the_deterministic_path_writes_a_checkpoint(config, agent):
    """It returned before reaching the writer, so a task whose phases are all
    deterministically checkable produced no checkpoint at all."""
    t = _task(config, agent)
    (ses.work_dir_for(agent, t)).mkdir(parents=True, exist_ok=True)
    (ses.work_dir_for(agent, t) / "out.txt").write_text("x")
    ses._verify_phase(config, agent, t, verifier=lambda **k: {"state": "FAIL"},
                      evidence="", engine="claude", index=0, now=time.time)
    assert ck.path_for(agent, t.id).exists()


def test_a_checkpoint_that_did_not_reach_disk_says_so(config, agent, monkeypatch):
    t = _task(config, agent)
    monkeypatch.setattr(os, "replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(ck.CheckpointNotWritten):
        ck.write(config, agent, t)
    assert not list(tsk.dir_of(agent, t.id).glob("*.tmp"))


def test_a_restart_refuses_to_resume_a_rewritten_plan(config, agent):
    """W3's real requirement. `resume_point()` had no caller at all — the live
    path read `earliest_incomplete()`, which resumes at the right number and
    has no idea the number now means different work."""
    t = _task(config, agent, criteria=("a.txt exists", "b.txt exists", "c.txt exists"))
    wd = ses.work_dir_for(agent, t)
    wd.mkdir(parents=True, exist_ok=True)
    for f in ("a.txt", "b.txt"):
        (wd / f).write_text("x")
    for i in (0, 1):
        t = ses._verify_phase(config, agent, t, verifier=lambda **k: {"state": "FAIL"},
                              evidence="", engine="claude", index=i, now=time.time)
    assert "Resume at phase 3" in ses._acp_resume_brief(config, agent, t)

    t.criteria = ["a totally different first thing", "and a second"]
    tsk._save(agent, t)
    brief = ses._acp_resume_brief(config, agent, t)
    assert "STOP" in brief and "rebase" in brief


def test_a_judged_task_cannot_be_assigned_without_a_forecast(config, agent):
    """The comment said the raise enforced the pre-action invariant; the
    blanket except below swallowed it, and a session was spawned anyway."""
    t = _task(config, agent)
    t = tsk.finish(config, agent, t, verdict={"state": "PASS", "why": "done"})
    t.session = None
    tsk._save(agent, t)
    with pytest.raises(fc.TooLate):
        ses.assign(config, agent, t, runtime=Runtime(), installed=lambda: set())


# ── consolidation: no trigger silently falls between the arms ───────────────

def test_rollback_episodes_reach_the_consolidator(config, agent):
    """Its outcome is `rolled_back`, so it missed the failure arm AND the
    success arm — a declared hard trigger that could never become anything."""
    for _ in range(4):
        memory.record(config, agent, "rollback", "goal changed from X to Y", "d")
    report = consolidate.run(config, agent)
    assert report["semantic_candidates"], "rollback produced no candidate"


def test_a_candidate_carries_the_real_weight_of_its_evidence(config, agent):
    for _ in range(4):
        memory.record(config, agent, "refusal", "the export timed out at 60s", "d")
    cand = consolidate.run(config, agent)["semantic_candidates"][0]
    assert cand["support_count"] == 4
    assert len(cand["provenance"]) == 4


def test_scope_covers_every_task_the_evidence_came_from(config, agent):
    """It kept the first two, so a rule evidenced by four tasks would not be
    retrieved for two of them — a silent cap on where the rule applies."""
    for i in range(4):
        memory.record_episode(config, agent, trigger="refusal",
                              summary="the same failure everywhere",
                              task_id=f"tsk_{i}")
    cand = consolidate.run(config, agent)["semantic_candidates"][0]
    assert len(cand["scope"]) == 4
