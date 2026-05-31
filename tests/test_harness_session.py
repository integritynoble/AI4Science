from __future__ import annotations

from pathlib import Path
from ai4science.harness.events import Message, TextDelta, ToolCall, Usage, Done
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.session import AgentSession
from ai4science.harness.tools import default_registry


def test_session_runs_tool_then_finishes(tmp_path):
    (tmp_path / "a.py").write_text("print('x')\n")
    script = [
        [TextDelta("reading "), ToolCall("c1", "read", {"path": "a.py"}), Usage(5, 2, 7), Done("tool_use")],
        [TextDelta("the file prints x."), Usage(3, 1, 4), Done("end")],
    ]
    metered = []
    sess = AgentSession(
        adapter=StubAdapter(script), model="stub", backend="anthropic",
        workspace=tmp_path, registry=default_registry(),
        read_only=False, auto_yes=True,
        on_text=lambda t: None,
        meter=lambda usage: metered.append(usage),
    )
    final = sess.run_turn("what does a.py do?")
    assert "prints x" in final
    roles = [m.role for m in sess.history]
    assert roles[0] == "user"
    assert any(m.role == "tool" for m in sess.history)
    assert sess.history[-1].role == "assistant"
    assert len(metered) == 2


def test_session_respects_read_only(tmp_path):
    script = [
        [ToolCall("c1", "write", {"path": "new.py", "content": "x"}), Done("tool_use")],
        [TextDelta("could not write."), Done("end")],
    ]
    sess = AgentSession(
        adapter=StubAdapter(script), model="stub", backend="anthropic",
        workspace=tmp_path, registry=default_registry(),
        read_only=True, auto_yes=False, on_text=lambda t: None, meter=lambda u: None,
    )
    sess.run_turn("create new.py")
    assert not (tmp_path / "new.py").exists()
    tool_msgs = [m for m in sess.history if m.role == "tool"]
    assert tool_msgs and "read-only" in tool_msgs[0].content.lower()
