"""The worker's lessons live in a DIFFERENT workspace from its tasks.

A sarsi-worker has two homes on this fleet, and neither is wrong:

    ~/.sarsi/agents/<id>/            the harness's — tasks, plans, memory/
    ~/.openclaw/workspace-<id>/      openclaw's    — AGENTS.md, MEMORY.md, memory/

`workspace_context()` read only the first. Measured on a live account: the
harness `memory/MEMORY.md` did not exist, openclaw's held **29 lessons**, and
the context came back with the task board and no lessons at all -- silently,
because a missing file is not an error.

So the worker could see WHAT it was doing and not WHAT IT HAD LEARNED, including
lessons its own workspace had recorded (*"a liveness guard matched its own
process and called a dead run alive"*).

Reading both is the fix, and the ordering matters: whichever is present
contributes, both contribute when both exist, and a line present in both is not
shown twice.
"""
import json
import pytest

from ai4science.harness.agents.sarsi import (selfaware, registry as reg,
                                             memory as mem)


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


def _openclaw_memory(home, agent_id, body):
    d = home / ".openclaw" / ("workspace-" + agent_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "MEMORY.md").write_text(body)
    return d


def test_openclaw_lessons_reach_the_context(config, tmp_path, monkeypatch):
    """The live case: harness memory absent, openclaw memory populated."""
    monkeypatch.setenv("HOME", str(tmp_path))
    a = config.agents["sarsi-worker"]
    _openclaw_memory(tmp_path, a.id,
                     "# MEMORY\n\n- [A guard matched its own process](memory/x.md) — it called a dead run alive\n")
    ctx = selfaware.workspace_context(config, a)
    assert "matched its own process" in ctx


def test_harness_lessons_still_reach_the_context(config, tmp_path, monkeypatch):
    """Reading the second source must not drop the first."""
    monkeypatch.setenv("HOME", str(tmp_path))
    a = config.agents["sarsi-worker"]
    idx = mem.index_path(config, a)
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("# MEMORY\n\n- [Harness lesson](l.md) — from the harness tree\n")
    ctx = selfaware.workspace_context(config, a)
    assert "from the harness tree" in ctx


def test_both_are_merged_without_duplicating(config, tmp_path, monkeypatch):
    """A lesson recorded in both trees is one lesson, not two."""
    monkeypatch.setenv("HOME", str(tmp_path))
    a = config.agents["sarsi-worker"]
    shared = "- [Shared](s.md) — written into both trees"
    idx = mem.index_path(config, a)
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("# MEMORY\n\n" + shared + "\n- [Only harness](h.md) — h\n")
    _openclaw_memory(tmp_path, a.id, "# MEMORY\n\n" + shared + "\n- [Only openclaw](o.md) — o\n")
    ctx = selfaware.workspace_context(config, a)
    assert ctx.count("written into both trees") == 1
    assert "Only harness" in ctx and "Only openclaw" in ctx


def test_neither_present_is_not_an_error(config, tmp_path, monkeypatch):
    """No lessons anywhere must stay silent, not raise -- the task board is
    still worth returning on its own."""
    monkeypatch.setenv("HOME", str(tmp_path))
    a = config.agents["sarsi-worker"]
    ctx = selfaware.workspace_context(config, a)
    assert "memory (lessons)" not in ctx
