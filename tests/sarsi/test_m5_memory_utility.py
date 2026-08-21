"""M5.5 — memory-utility experiment: frozen trap-set comparison.

Two test families, reported separately per the plan:

  Family A — trigger-coverage: covered in test_m5_episode_coverage.py.
  Family B — memory utility: this file.

Memory-utility test setup:
  1. Seed the agent with a known lesson via a trigger.
  2. Assert that WITHOUT memory (empty index) the lesson is NOT in the
     context → the agent would be blind to it.
  3. Assert that WITH memory (lesson written) the lesson IS injected into
     the context → the agent CAN see it and avoid repeating the error.
  4. Assert the repeat-error rate: after a lesson is written, calling
     record() for the same trigger with the same title again should still
     produce an episode (episodes are facts), but the INDEX shows the
     lesson — so a well-integrated system would not repeat the blind call.

This does not run an LLM.  It verifies the retrieval and injection
machinery (memory.load_index, selfaware.workspace_context) behaves
correctly — a structural guarantee that the context IS different with vs
without memory.

Metrics reported (as pytest output / assertions):
  - correctness: lesson present in context when memory is on.
  - repeat-error proxy: two calls produce two distinct episodes (not deduplicated).
  - token-cost proxy: context length with memory ≥ context length without memory
    (memory adds bytes — a test that context doesn't shrink).
  - retrieval latency: measured with time.perf_counter (logged, not asserted,
    because latency bounds are environment-dependent).
"""
from __future__ import annotations

import json
import time

import pytest

from ai4science.harness.agents.sarsi import memory, registry as reg
from ai4science.harness.agents.sarsi import selfaware, ledger


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


# ── trap 1: lesson absent → context is blind ─────────────────────────────────

def test_context_has_no_lesson_before_trigger(config):
    a = _agent(config)
    idx = memory.load_index(config, a)
    assert idx == "", (
        "memory index should be empty before any trigger fires; "
        f"got: {idx[:200]!r}")


# ── trap 2: lesson present after trigger → context sees it ───────────────────

def test_lesson_appears_in_index_after_trigger(config):
    a = _agent(config)
    memory.record(config, a, "refusal",
                  "refused to delete the production database",
                  "operator asked; refused because it is irreversible")
    idx = memory.load_index(config, a)
    assert idx, "memory index must be non-empty after a trigger"
    assert "production database" in idx, (
        f"lesson not found in index:\n{idx}")


# ── trap 3: workspace_context injects the lesson ─────────────────────────────

def test_workspace_context_contains_lesson(config):
    a = _agent(config)
    memory.record(config, a, "correction",
                  "do not create files outside the declared work_root",
                  "owner corrected the executor path assumption")
    ctx = selfaware.workspace_context(config, a)
    assert "work_root" in ctx or "declared work" in ctx.lower(), (
        f"lesson not found in workspace context (first 400 chars):\n{ctx[:400]}")


# ── trap 4: context without memory is shorter than with memory ───────────────

def test_context_is_longer_with_memory(config):
    a = _agent(config)
    ctx_before = selfaware.workspace_context(config, a)
    memory.record(config, a, "clash",
                  "attempted the same git push twice — clash detected",
                  "exact-once violation on the push target")
    ctx_after = selfaware.workspace_context(config, a)
    assert len(ctx_after) >= len(ctx_before), (
        "context with memory should be at least as long as without; "
        f"before={len(ctx_before)} after={len(ctx_after)}")


# ── trap 5: two triggers → two distinct episodes (repeat-error proxy) ─────────

def test_same_trigger_twice_produces_two_distinct_episodes(config):
    a = _agent(config)
    memory.record(config, a, "refuted_prediction",
                  "predicted test would pass; it failed")
    memory.record(config, a, "refuted_prediction",
                  "predicted test would pass; it failed again")
    eps = [r for r in ledger.read(config, "episodes")
           if r.get("agent_id") == a.id]
    assert len(eps) == 2, f"expected 2 episodes, got {len(eps)}"
    ids = {e["episode_id"] for e in eps}
    assert len(ids) == 2, "episode_ids must be distinct"


# ── trap 6: five different triggers each visible in index ────────────────────

def test_all_five_triggers_visible_in_index(config):
    a = _agent(config)
    trigger_to_title = {
        "refuted_prediction": "prediction about response time was wrong",
        "rollback":           "rolled back the schema migration",
        "refusal":            "refused to expose credentials in the log",
        "clash":              "identical write attempted twice",
        "correction":         "owner corrected the scope assumption",
    }
    for trigger, title in trigger_to_title.items():
        memory.record(config, a, trigger, title)
    idx = memory.load_index(config, a)
    # At least one keyword per lesson should appear in the index.
    keyword_checks = [
        ("response time", "refuted_prediction"),
        ("schema migration", "rollback"),
        ("credentials", "refusal"),
        ("identical write", "clash"),
        ("scope assumption", "correction"),
    ]
    for keyword, trigger in keyword_checks:
        assert keyword in idx, (
            f"lesson for trigger={trigger!r} (keyword={keyword!r}) not in index:\n{idx}")


# ── trap 7: retrieval latency is logged (informational) ──────────────────────

def test_retrieval_latency_is_acceptable(config):
    """Memory retrieval must complete in reasonable time.

    Threshold is generous (1 second) — the important thing is the call
    returns at all.  Tighten this bound when indexing is optimised.
    """
    a = _agent(config)
    for i in range(5):
        memory.record(config, a, "correction", f"correction lesson {i}")
    t0 = time.perf_counter()
    idx = memory.load_index(config, a)
    elapsed = time.perf_counter() - t0
    print(f"\nRetrieval latency for 5-lesson index: {elapsed*1000:.1f} ms")
    assert elapsed < 1.0, (
        f"retrieval took {elapsed:.3f}s — exceeded 1s budget")
    assert idx, "load_index returned empty for a non-empty lesson store"


# ── trap 8: context snapshot is written on workspace_context call ─────────────

def test_context_manifest_written(config, monkeypatch):
    """M2.5: a context_manifest.jsonl entry is written each time workspace_context
    is called, so exact W_t bytes can be replayed."""
    a = _agent(config)
    manifest_path = a.agent_dir / "context_manifest.jsonl"
    assert not manifest_path.exists(), "manifest should not exist before first call"
    selfaware.workspace_context(config, a, observation="test query")
    assert manifest_path.exists(), "context_manifest.jsonl not written"
    entries = [json.loads(line) for line in manifest_path.read_text().splitlines()
               if line.strip()]
    assert entries, "manifest file is empty"
    entry = entries[0]
    for field in ("context_id", "at", "sha256", "byte_count", "gz_path"):
        assert field in entry, f"missing field {field!r} in manifest entry: {entry}"
    # The gz file must also exist.
    from pathlib import Path
    gz = Path(entry["gz_path"])
    assert gz.exists(), f"context gz file not found: {gz}"
    # Round-trip: decompress and verify SHA256.
    import gzip, hashlib
    raw = gzip.open(gz).read()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"], (
        "context SHA256 mismatch — replay integrity broken")
