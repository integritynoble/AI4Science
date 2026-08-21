"""M5.5 — trigger-coverage tests.

Each declared hard trigger produces exactly one episode in the ledger when
`memory.record()` is called, and no duplicate episodes are produced by a
single call.

Invariants:
- TRIGGERS = ("refuted_prediction", "rollback", "refusal", "clash", "correction")
- One call to memory.record(trigger=T) → one episode in episodes ledger.
- episode.trigger == T
- episode.outcome matches the expected default for T
- episode.agent_id == agent.id
- episode.lesson_ref is non-empty (points to the lesson file name)
- A second call with the same trigger appends a second distinct episode,
  not a duplicate of the first (different episode_id).
- An unknown trigger writes no episode (record() returns None).
- record_episode() called directly also writes exactly one ledger row.
"""
from __future__ import annotations

import json

import pytest

from ai4science.harness.agents.sarsi import ledger, memory, registry as reg
from ai4science.harness.agents.sarsi.memory import TRIGGERS


# ── fixture ───────────────────────────────────────────────────────────────────

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


def _episodes(config, agent):
    return [r for r in ledger.read(config, "episodes")
            if r.get("agent_id") == agent.id]


# ── one trigger → one episode ─────────────────────────────────────────────────

@pytest.mark.parametrize("trigger,expected_outcome", [
    ("refuted_prediction", "fail"),
    ("rollback",           "rolled_back"),
    ("refusal",            "refused"),
    ("clash",              "fail"),
    ("correction",         "rolled_back"),
])
def test_each_trigger_writes_exactly_one_episode(config, trigger, expected_outcome):
    a = _agent(config)
    before = _episodes(config, a)

    memory.record(config, a, trigger, f"test lesson for {trigger}", "detail")

    after = _episodes(config, a)
    new = [e for e in after if e not in before]
    assert len(new) == 1, (
        f"trigger={trigger!r}: expected 1 new episode, got {len(new)}: {new}")
    ep = new[0]
    assert ep["trigger"] == trigger, ep
    assert ep["outcome"] == expected_outcome, ep
    assert ep["agent_id"] == a.id, ep


def test_episode_has_non_empty_lesson_ref(config):
    a = _agent(config)
    memory.record(config, a, "refusal", "refused a bad brief", "no detail needed")
    eps = _episodes(config, a)
    assert eps, "no episodes written"
    assert eps[-1]["lesson_ref"], "lesson_ref is empty"


def test_episode_summary_matches_title(config):
    a = _agent(config)
    title = "prediction failed on network task"
    memory.record(config, a, "refuted_prediction", title)
    ep = _episodes(config, a)[-1]
    assert title in ep["summary"], ep


# ── two calls → two distinct episodes ────────────────────────────────────────

def test_second_call_adds_second_distinct_episode(config):
    a = _agent(config)
    memory.record(config, a, "clash", "clash A", "detail A")
    memory.record(config, a, "clash", "clash B", "detail B")
    eps = _episodes(config, a)
    assert len(eps) == 2, f"expected 2 episodes, got {len(eps)}"
    ids = {e["episode_id"] for e in eps}
    assert len(ids) == 2, f"duplicate episode_ids: {ids}"


# ── unknown trigger → no episode ─────────────────────────────────────────────

def test_unknown_trigger_writes_no_episode(config):
    a = _agent(config)
    result = memory.record(config, a, "not_a_trigger", "should be ignored")
    assert result is None, "expected None for unknown trigger"
    eps = _episodes(config, a)
    assert len(eps) == 0, f"unexpected episode written: {eps}"


# ── all five triggers produce episodes ───────────────────────────────────────

def test_all_five_triggers_produce_episodes(config):
    a = _agent(config)
    for trigger in TRIGGERS:
        memory.record(config, a, trigger, f"lesson for {trigger}")
    eps = _episodes(config, a)
    assert len(eps) == len(TRIGGERS), (
        f"expected {len(TRIGGERS)} episodes, got {len(eps)}")
    triggers_seen = {e["trigger"] for e in eps}
    assert triggers_seen == set(TRIGGERS), (
        f"missing triggers: {set(TRIGGERS) - triggers_seen}")


# ── record_episode() directly ─────────────────────────────────────────────────

def test_record_episode_directly_writes_one_row(config):
    a = _agent(config)
    ep = memory.record_episode(config, a, "rollback", "direct episode write",
                               task_id="tsk_test", tags=["direct"])
    eps = _episodes(config, a)
    assert len(eps) == 1, f"expected 1 episode, got {len(eps)}"
    assert eps[0]["episode_id"] == ep["episode_id"]
    assert eps[0]["task_id"] == "tsk_test"
    assert "direct" in eps[0]["tags"]


def test_record_episode_schema_fields_present(config):
    a = _agent(config)
    ep = memory.record_episode(config, a, "correction", "schema check",
                               phase_id="ph_1", lesson_ref="20240101-correction-foo.md")
    required = ("schema_version", "episode_id", "agent_id", "trigger",
                 "outcome", "summary", "started_at", "ended_at")
    for field in required:
        assert field in ep, f"missing field {field!r} in episode: {ep}"
    assert ep["schema_version"] == 1
    assert ep["phase_id"] == "ph_1"
    assert ep["lesson_ref"] == "20240101-correction-foo.md"


# ── episode survives a ledger round-trip ─────────────────────────────────────

def test_episode_survives_round_trip(config):
    a = _agent(config)
    memory.record(config, a, "correction", "round-trip lesson", "extra detail")
    from_ledger = _episodes(config, a)
    assert from_ledger, "no episodes in ledger"
    ep = from_ledger[-1]
    assert ep["trigger"] == "correction"
    assert ep["summary"] == "round-trip lesson"
