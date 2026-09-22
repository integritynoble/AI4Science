"""Approved project state lives outside the chat (A03): the owner approves,
the agent proposes, and the current state is what the model sees every turn."""
from __future__ import annotations

import json

import pytest

from ai4science.harness.events import Message
from ai4science.harness.runtime import decisions as d


def test_only_the_owner_approves_and_the_latest_approval_wins(tmp_path):
    j = d.Journal(tmp_path)
    with pytest.raises(PermissionError):
        j.approve("dataset", "v3", source="agent:propose")
    a1 = j.approve("dataset", "v1", source="owner:/approve")
    p = j.propose("dataset", "v3", source="agent:propose", why="newest file")
    assert j.current()["dataset"].value == "v1"                # a proposal changes nothing
    assert [r.id for r in j.pending()] == [p.id]
    a2 = j.approve("dataset", "v2", source="owner:/approve")
    assert j.current()["dataset"].value == "v2" and a2.supersedes == a1.id
    j.reject(p.id, source="owner:/reject", why="not approved")
    assert j.pending() == []
    assert j.current()["dataset"].value == "v2"
    with pytest.raises(ValueError):
        j.reject(p.id, source="owner:/reject")                  # already decided
    ok = j.propose("threshold", "0.5", source="agent:propose")
    ap = j.approve_proposal(ok.id, source="owner:/approve")
    assert ap.supersedes == ok.id and j.current()["threshold"].value == "0.5"
    assert j.pending() == []


def test_journal_survives_a_torn_tail_and_has_lineage(tmp_path):
    j = d.Journal(tmp_path)
    j.approve("k", "v", source="owner:/approve")
    j.path.write_text(j.path.read_text() + '{"id": 2, "key": "k", "val')
    assert j.current()["k"].value == "v"
    r = j.current()["k"]
    assert r.source == "owner:/approve" and r.ts > 0 and r.id == 1
    with pytest.raises(ValueError):
        j.propose("", "x", source="agent:propose")


def test_state_message_is_placed_after_the_prompt_and_refreshed(tmp_path):
    j = d.Journal(tmp_path)
    hist = [Message(role="system", content="MODE"), Message(role="user", content="hi"),
            Message(role="assistant", content="yo")]
    d.refresh_state_message(hist, j)
    assert [m.role for m in hist] == ["system", "user", "assistant"]    # empty journal: nothing
    j.approve("dataset", "v2", source="owner:/approve")
    j.propose("dataset", "v3", source="agent:propose")
    d.refresh_state_message(hist, j)
    assert hist[0].content == "MODE" and hist[1].content.startswith(d.STATE_MARK)
    assert "dataset = v2" in hist[1].content and "NOT approved" in hist[1].content
    assert "#2 dataset = v3" in hist[1].content
    d.refresh_state_message(hist, j)                            # idempotent
    assert sum(1 for m in hist if m.content.startswith(d.STATE_MARK)) == 1
    # after a compaction summary the state still goes right after the prompt
    hist.insert(1, Message(role="system", content="[compacted earlier conversation]\nS"))
    hist = [m for m in hist if not m.content.startswith(d.STATE_MARK)]
    d.refresh_state_message(hist, j)
    assert hist[1].content.startswith(d.STATE_MARK) and hist[2].content.startswith("[compacted")


def test_tools_propose_but_never_approve(tmp_path):
    tools = {t.name: t for t in d.decision_tools(tmp_path)}
    assert not tools["decisions"].mutating and not tools["propose_decision"].mutating
    assert "no approved decisions" in tools["decisions"].func(tmp_path)
    out = tools["propose_decision"].func(tmp_path, key="dataset", value="v3", why="newest")
    assert "NOT approved" in out and "#1" in out
    j = d.Journal(tmp_path)
    assert j.current() == {} and j.pending()[0].source == "agent:propose"
    assert "Pending proposals" in tools["decisions"].func(tmp_path)
    assert tools["propose_decision"].func(tmp_path, key="", value="x").startswith("[error]")


def test_repl_slash_commands_drive_the_journal(tmp_path, monkeypatch, capsys):
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.repl import run_common_repl
    import ai4science.harness.repl as repl_mod
    from ai4science.llm import routing
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: StubAdapter([]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: True)
    inputs = iter(["/approve dataset=v2", "/decisions", "/approve", "/reject 9", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    run_common_repl(tmp_path, read_only=True, backend="anthropic", model="stub")
    out = capsys.readouterr().out
    assert "approved #1: dataset = v2" in out
    assert "dataset = v2   (approved #1, owner:/approve)" in out
    assert "usage: /approve" in out and "no open proposal #9" in out
    j = d.Journal(tmp_path)
    assert j.current()["dataset"].value == "v2"
    assert (tmp_path / ".ai4science" / "decisions.jsonl").exists()
