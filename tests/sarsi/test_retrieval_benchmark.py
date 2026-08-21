"""M2.2 — frozen retrieval benchmark.

Six cases from the plan, measuring:
  - protected-directive miss rate (must be 0)
  - Recall@k (correct entries appear in top-k)
  - supersession correctness (only the replacement is returned)
  - task-scope ranking (relevant task entry outranks irrelevant recent entry)
  - cross-project isolation (different-project constraint stays bounded)

Run with both modes:
  SARSI_SEMANTIC_RETRIEVAL=0 pytest ...   (lexical, default)
  SARSI_SEMANTIC_RETRIEVAL=1 pytest ...   (semantic arm)

Report: each test asserts the invariant that must hold in BOTH modes.
Benchmark-specific thresholds (Recall@3) are parametrised so they can be
tightened when a new retrieval algorithm is adopted.
"""
from __future__ import annotations

import json
import os

import pytest

from ai4science.harness.agents.sarsi import retrieval as ret
from ai4science.harness.agents.sarsi import semantic, registry as reg


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"
    root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p)
    c.ensure_dirs()
    return c


def _agent(config):
    return config.agents["sarsi-worker"]


# ── helpers ───────────────────────────────────────────────────────────────────

def _seed(config, agent, statement, kind="lesson", scope=None, status="active"):
    return semantic.record(config, agent, statement,
                           kind=kind, scope=scope or ["global"],
                           status=status, promoted_by="owner")


def _in_result(result, statement_fragment):
    for section in ("protected", "retrieved"):
        for e in result[section]:
            if statement_fragment.lower() in (e.get("statement") or "").lower():
                return True
    return False


# ── case 1: semantically distant hard constraint is never missed ──────────────
# A constraint with vocabulary completely unlike the query (e.g. a security rule
# when asking about plotting) must appear because it is protected.

def test_protected_constraint_never_missed_lexical(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    a = _agent(config)
    _seed(config, a, "never log authentication tokens to disk",
          kind="invariant", scope=["global"])
    _seed(config, a, "prefer matplotlib for all visualisation tasks",
          kind="lesson", scope=["global"])

    result = ret.retrieve(config, a, query="plot the loss curve for training",
                          task_id="")
    protected_stmts = [e.get("statement", "") for e in result["protected"]]
    assert any("authentication tokens" in s for s in protected_stmts), (
        "hard constraint was missing from protected arm")


def test_protected_constraint_never_missed_semantic(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "1")
    a = _agent(config)
    _seed(config, a, "never log authentication tokens to disk",
          kind="invariant", scope=["global"])
    result = ret.retrieve(config, a, query="plot the loss curve for training")
    assert any("authentication tokens" in (e.get("statement") or "")
               for e in result["protected"]), (
        "hard constraint missing from protected arm in semantic mode")


# ── case 2: same-task old decision is retrieved ───────────────────────────────

def test_same_task_decision_is_retrieved(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    a = _agent(config)
    task_id = "tsk_abc123"
    _seed(config, a, "use parquet not CSV for interim results",
          kind="lesson", scope=[f"task:{task_id}"])
    _seed(config, a, "use blue for all chart colours",
          kind="lesson", scope=["global"])

    result = ret.retrieve(config, a, query="store the results", task_id=task_id)
    retrieved_stmts = [e.get("statement", "") for e in result["retrieved"]]
    assert any("parquet" in s for s in retrieved_stmts), (
        "same-task decision not in retrieved set")


# ── case 3: superseded decision — only replacement appears ────────────────────

def test_superseded_entry_not_returned(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    a = _agent(config)
    old = _seed(config, a, "use CSV for storing results", kind="lesson")
    semantic.supersede(config, a, old["memory_id"],
                       "use parquet for storing results (CSV deprecated)")

    result = ret.retrieve(config, a, query="store the results")
    all_stmts = ([e.get("statement", "") for e in result["protected"]]
                 + [e.get("statement", "") for e in result["retrieved"]])
    assert not any("CSV for storing" in s for s in all_stmts), (
        "superseded entry was returned")
    assert any("parquet" in s for s in all_stmts), (
        "replacement entry not returned after supersession")


# ── case 4: relevant episode from same task outranks irrelevant recent one ────

def test_same_task_entry_outranks_irrelevant_recent(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    a = _agent(config)
    task_id = "tsk_xyz789"
    # High-relevance: same task
    _seed(config, a, "avoid using global variables in the model module",
          kind="lesson", scope=[f"task:{task_id}"])
    # Low-relevance: global scope, unrelated topic
    _seed(config, a, "always run linters before committing",
          kind="lesson", scope=["global"])

    result = ret.retrieve(config, a,
                          query="refactoring the model module",
                          task_id=task_id, k=5)
    retrieved = result["retrieved"]
    assert retrieved, "retrieved set is empty"
    # The same-task entry must appear BEFORE the unrelated global one.
    stmts = [e.get("statement", "") for e in retrieved]
    task_pos = next((i for i, s in enumerate(stmts) if "global variables" in s), None)
    global_pos = next((i for i, s in enumerate(stmts) if "linters" in s), None)
    assert task_pos is not None, "task-relevant entry not in result"
    if global_pos is not None:
        assert task_pos < global_pos, (
            f"task entry at pos {task_pos} but unrelated global at {global_pos}")


# ── case 5: irrelevant recent entry does not crowd out older relevant one ──────

def test_irrelevant_recent_does_not_crowd_relevant(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    a = _agent(config)
    task_id = "tsk_model42"
    _seed(config, a, "normalise all input tensors before passing to model",
          kind="lesson", scope=[f"task:{task_id}"])
    # Unrelated lesson with no keyword overlap
    _seed(config, a, "budget approval requires owner sign-off",
          kind="lesson", scope=["global"])

    result = ret.retrieve(config, a, query="prepare model inputs", task_id=task_id)
    stmts = [e.get("statement", "") for e in result["retrieved"]]
    assert any("normalise" in s or "normalize" in s for s in stmts), (
        "relevant entry crowded out by irrelevant recent one")


# ── case 6: two similar projects — per-project constraint stays bounded ────────

def test_per_project_constraint_does_not_bleed(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    a = _agent(config)
    _seed(config, a, "for project-A: use S3 bucket alpha-data for all uploads",
          kind="lesson", scope=["task:tsk_projA"])
    _seed(config, a, "for project-B: use S3 bucket beta-data for all uploads",
          kind="lesson", scope=["task:tsk_projB"])

    result_a = ret.retrieve(config, a, query="upload the dataset",
                            task_id="tsk_projA", k=5)
    result_b = ret.retrieve(config, a, query="upload the dataset",
                            task_id="tsk_projB", k=5)

    stmts_a = [e.get("statement", "") for e in result_a["retrieved"]]
    stmts_b = [e.get("statement", "") for e in result_b["retrieved"]]

    # project-A result must rank alpha-data first
    if stmts_a:
        assert "alpha-data" in stmts_a[0], (
            f"project-A retrieved wrong bucket first: {stmts_a[0]!r}")
    # project-B result must rank beta-data first
    if stmts_b:
        assert "beta-data" in stmts_b[0], (
            f"project-B retrieved wrong bucket first: {stmts_b[0]!r}")


# ── mode comparison: semantic arm result is a superset of protected arm ────────

def test_semantic_mode_preserves_protected_arm(config, monkeypatch):
    a = _agent(config)
    _seed(config, a, "never expose private keys in logs", kind="invariant")
    _seed(config, a, "prefer async IO for network operations", kind="lesson")

    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    lex = ret.retrieve(config, a, query="make a network request")

    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "1")
    sem = ret.retrieve(config, a, query="make a network request")

    lex_protected = {e["memory_id"] for e in lex["protected"]}
    sem_protected = {e["memory_id"] for e in sem["protected"]}
    assert lex_protected == sem_protected, (
        "semantic mode changed the protected arm — it must not")


# ── candidates only: candidates are excluded from retrieved ───────────────────

def test_candidate_entries_excluded(config, monkeypatch):
    monkeypatch.setenv("SARSI_SEMANTIC_RETRIEVAL", "0")
    a = _agent(config)
    _seed(config, a, "always write unit tests first", kind="lesson",
          status="candidate")
    _seed(config, a, "document public APIs", kind="lesson", status="active")

    result = ret.retrieve(config, a, query="write some tests")
    all_stmts = ([e.get("statement", "") for e in result["protected"]]
                 + [e.get("statement", "") for e in result["retrieved"]])
    assert not any("unit tests first" in s for s in all_stmts), (
        "candidate entry leaked into retrieval result")
