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
