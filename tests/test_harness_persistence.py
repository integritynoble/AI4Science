from __future__ import annotations

from pathlib import Path
from ai4science.harness.events import ImagePart, Message, ToolCall
from ai4science.harness import persistence


def test_roundtrip_history(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    history = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="reading", tool_calls=[ToolCall("c1", "read", {"path": "a"})]),
        Message(role="tool", content="data", tool_call_id="c1"),
    ]
    persistence.save("sess1", tmp_path / "ws", history)
    loaded = persistence.load("sess1")
    assert [m.role for m in loaded] == ["user", "assistant", "tool"]
    assert loaded[1].tool_calls[0].name == "read"
    assert loaded[2].tool_call_id == "c1"


def test_roundtrip_preserves_images(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    history = [Message(role="user", content="look",
                       images=[ImagePart("image/png", "AAAA")])]
    persistence.save("imgsess", tmp_path / "ws", history)
    loaded = persistence.load("imgsess")
    assert loaded[0].images and loaded[0].images[0].media_type == "image/png"
    assert loaded[0].images[0].data_b64 == "AAAA"


def test_most_recent_for_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    ws = tmp_path / "ws"
    persistence.save("old", ws, [Message(role="user", content="1")])
    persistence.save("new", ws, [Message(role="user", content="2")])
    assert persistence.most_recent(ws) == "new"


# ── a kill mid-save leaves the previous file; a damaged file still resumes ──

def test_save_is_atomic_no_partial_file_on_failure(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    ws = tmp_path / "ws"
    persistence.save("s", ws, [Message(role="user", content="first")])
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("killed")))
    try:
        persistence.save("s", ws, [Message(role="user", content="first"),
                                   Message(role="user", content="second")])
    except OSError:
        pass
    monkeypatch.setattr(os, "replace", real_replace)
    assert [m.content for m in persistence.load("s")] == ["first"]     # the old file, intact


def test_load_skips_torn_lines_and_marks_unresolved_tool_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    ws = tmp_path / "ws"
    persistence.save("t", ws, [
        Message(role="user", content="hi"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "read", {"path": "a"})]),
        Message(role="tool", content="data", tool_call_id="c1"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c2", "read", {"path": "b"}),
                                                          ToolCall("c3", "read", {"path": "c"})]),
        Message(role="tool", content="only one of two answered", tool_call_id="c2"),
    ])
    p = tmp_path / "t.jsonl"
    p.write_text(p.read_text() + '{"role": "assistant", "content": "torn')
    hist = persistence.load("t")
    assert [m.role for m in hist] == ["user", "assistant", "tool", "assistant", "tool", "tool"]
    assert hist[-2].tool_call_id == "c2"
    assert hist[-1].tool_call_id == "c3"
    assert "unresolved after recovery" in hist[-1].content


def test_unreadable_index_does_not_break_save_or_load(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    (tmp_path / "index.json").write_text("{not json")
    ws = tmp_path / "ws"
    persistence.save("u", ws, [Message(role="user", content="x")])
    assert persistence.most_recent(ws) == "u"
    assert [m.content for m in persistence.load("u")] == ["x"]


def test_private_files_and_fsync_failure_propagates(tmp_path, monkeypatch):
    import os
    import pytest
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    persistence.save("private", tmp_path, [Message(role="user", content="secret")])
    if os.name == "posix":
        assert (tmp_path / "private.jsonl").stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "index.json").stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        persistence.save("private", tmp_path, [Message(role="user", content="changed")])
    assert persistence.load("private")[0].content == "secret"
