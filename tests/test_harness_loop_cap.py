from __future__ import annotations

from pathlib import Path
from ai4science.harness import loop as loop_mod
from ai4science.harness.events import Message, ToolCall, Done
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools import default_registry


class _AlwaysToolAdapter:
    def stream(self, history, tools, *, model, reasoning):
        yield ToolCall("c1", "read", {"path": "a.py"})
        yield Done("tool_use")


def test_loop_cap_emits_truncation_signal(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x\n")
    monkeypatch.setattr(loop_mod, "MAX_TOOL_ITERATIONS", 3)
    texts = []
    history = [Message(role="user", content="go")]
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    out = loop_mod.run_loop(
        adapter=_AlwaysToolAdapter(), model="stub", reasoning="low",
        history=history, workspace=tmp_path, registry=default_registry(),
        gate=gate, on_text=texts.append, meter=lambda u: None,
    )
    assert "3 tool iterations" in out.lower() or "truncat" in out.lower()
    assert any("iteration" in t.lower() for t in texts)
