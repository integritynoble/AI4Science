"""What the model actually saw, reproduced byte for byte. [plan v3 §7.4, §11.4]

A context hash plus section byte counts cannot rebuild an input after the
source files change — the memory moves on and the hash then proves only that
something is different. So the exact rendered snapshot is stored beside a
manifest, and the manifest carries what the bytes cannot say for themselves:
which ids were selected, what was left out, the budget in force, and the mode
and router version that chose them.

Without those last two, a bad answer cannot be attributed. A routing mistake
and a retrieval mistake look identical in the bytes.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (log, mode, registry as reg,
                                             selfaware as sa, semantic)


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


def _last(agent):
    return sa.manifest(agent.agent_dir)[-1]


def test_a_stored_context_id_reproduces_the_exact_bytes(config, agent):
    log.append(agent.agent_dir, "cli", "how does the gate work?", "it assembles W_t")
    ctx = sa.workspace_context(config, agent, observation="why?",
                               route=mode.route("why?"))
    back = sa.replay(agent.agent_dir, _last(agent)["context_id"])
    assert back == ctx


def test_the_manifest_names_the_ids_the_budget_and_what_was_left_out(config, agent):
    for i in range(30):
        log.append(agent.agent_dir, "cli", f"turn {i} " + "x" * 400,
                   f"reply {i} " + "y" * 400)
    sa.workspace_context(config, agent, observation="why?",
                         route=mode.route("why?"))
    row = _last(agent)
    assert row["sha256"] and row["byte_count"] > 0
    assert row["budget"]["recent_tokens"] > 0
    assert row["selected"]["exchanges"]              # which exchanges got in
    assert row["omitted"]["older_exchanges"] > 0     # and how many did not
    assert [s["name"] for s in row["sections"]]      # ordering, with sizes
    assert row["token_estimator"]                    # which estimator measured it


def test_the_mode_and_the_router_that_chose_it_are_recorded(config, agent):
    sa.workspace_context(config, agent, observation="implement M2",
                         route=mode.route("implement the M2 gate"))
    row = _last(agent)
    assert row["mode"] == "ACTION"
    assert row["router_version"] == mode.ROUTER_VERSION
    assert row["route"]["signals"]


def test_changing_memory_later_does_not_change_the_historical_snapshot(config, agent):
    """The whole point. Memory moves on; what a past turn saw does not."""
    semantic.record(config, agent, "the exporter writes CSV only",
                    kind="invariant", scope=["global"], provenance="owner")
    sa.workspace_context(config, agent, observation="implement M2",
                         route=mode.route("implement the M2 gate"))
    ctx_id = _last(agent)["context_id"]
    before = sa.replay(agent.agent_dir, ctx_id)
    assert "writes CSV only" in before

    semantic.record(config, agent, "the exporter now writes parquet",
                    kind="invariant", scope=["global"], provenance="owner")
    sa.workspace_context(config, agent, observation="implement M2",
                         route=mode.route("implement the M2 gate"))
    assert sa.replay(agent.agent_dir, ctx_id) == before
    assert "parquet" not in before


def test_a_snapshot_that_does_not_match_its_manifest_is_not_evidence(config, agent):
    import gzip
    sa.workspace_context(config, agent, observation="hello",
                         route=mode.route("hello"))
    row = _last(agent)
    with gzip.open(row["gz_path"], "wb") as fh:
        fh.write(b"something else entirely")
    assert sa.replay(agent.agent_dir, row["context_id"]) is None


def test_an_unknown_context_id_replays_as_nothing(config, agent):
    assert sa.replay(agent.agent_dir, "ctx_doesnotexist") is None


def test_old_manifest_rows_are_still_readable(config, agent):
    """A v1 row (no mode, no sections) predates the router. It must load."""
    agent.agent_dir.mkdir(parents=True, exist_ok=True)
    p = agent.agent_dir / "context_manifest.jsonl"
    p.write_text(json.dumps({"context_id": "ctx_old", "at": "2026-08-21T00:00:00+00:00",
                             "sha256": "deadbeef", "byte_count": 10,
                             "gz_path": "/nowhere.gz"}) + "\n")
    rows = sa.manifest(agent.agent_dir)
    assert rows[0]["context_id"] == "ctx_old"
    assert "mode" not in rows[0]                 # not invented on read
    assert sa.replay(agent.agent_dir, "ctx_old") is None
