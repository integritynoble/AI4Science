"""The workspace must survive the absence of the harness registry.

Most accounts of this fleet have no ``~/.sarsi/sarsi.json``. The REPL's caller
wraps the whole lookup in a bare ``except: pass``, so before this the worker
answered with no workspace at all and said nothing about it.
"""
import os
from pathlib import Path

from ai4science.harness.agents.sarsi import selfaware


def _openclaw_memory(home: Path, agent_id: str, body: str) -> None:
    ws = home / ".openclaw" / ("workspace-" + agent_id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "MEMORY.md").write_text(body)


def test_lessons_reach_context_with_no_harness_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    _openclaw_memory(tmp_path, "sarsi-worker",
                     "# Memory\n- [A green checkmark is not the event](m/g.md) — proof\n")
    out = selfaware.openclaw_workspace_context("sarsi-worker")
    assert "green checkmark" in out
    assert "workspace" in out


def test_empty_when_the_worker_has_no_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    assert selfaware.openclaw_workspace_context("sarsi-worker") == ""


def test_empty_id_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    assert selfaware.openclaw_workspace_context("") == ""


def test_headings_are_not_offered_as_lessons(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    _openclaw_memory(tmp_path, "sarsi-worker", "# Memory\n\n- [Real lesson](m/r.md) — x\n")
    out = selfaware.openclaw_workspace_context("sarsi-worker")
    assert "Real lesson" in out
    assert "# Memory" not in out
