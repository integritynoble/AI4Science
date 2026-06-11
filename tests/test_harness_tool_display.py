"""Native-loop tool visibility — Claude Code parity.

Claude Code shows a collapsed line per tool call (`⏺ Bash(ls …)`) and a dim
result gutter (`⎿ 12 lines`). The native harness loop previously executed
read-only tools silently. run_loop now fires on_tool_start/on_tool_end so the
REPL can render the same collapsed lines (toolfmt formats them).
"""
from __future__ import annotations

from ai4science.harness import loop as loop_mod
from ai4science.harness import toolfmt
from ai4science.harness.events import Message, ToolCall, Done
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools import default_registry


class _OneToolAdapter:
    """First stream emits one read call; second stream ends the turn."""
    def __init__(self):
        self.n = 0

    def stream(self, history, tools, *, model, reasoning):
        self.n += 1
        if self.n == 1:
            yield ToolCall("c1", "read", {"path": "a.py"})
        yield Done("stop")


def _run(adapter, tmp_path, **kw):
    history = [Message(role="user", content="go")]
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    return loop_mod.run_loop(
        adapter=adapter, model="stub", reasoning="low",
        history=history, workspace=tmp_path, registry=default_registry(),
        gate=gate, on_text=lambda t: None, meter=lambda u: None, **kw)


def test_loop_fires_tool_start_and_end(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    starts, ends = [], []
    _run(_OneToolAdapter(), tmp_path,
         on_tool_start=lambda name, args: starts.append((name, args)),
         on_tool_end=lambda name, result: ends.append((name, result)))
    assert starts == [("read", {"path": "a.py"})]
    assert len(ends) == 1
    assert ends[0][0] == "read" and "x = 1" in str(ends[0][1])


def test_loop_reports_blocked_calls_to_on_tool_end(tmp_path):
    class _WriteAdapter(_OneToolAdapter):
        def stream(self, history, tools, *, model, reasoning):
            self.n += 1
            if self.n == 1:
                yield ToolCall("c1", "write", {"path": "a.py", "content": "x"})
            yield Done("stop")

    ends = []
    _run(_WriteAdapter(), tmp_path,
         on_tool_end=lambda name, result: ends.append((name, result)))
    assert len(ends) == 1 and "[blocked]" in str(ends[0][1])


def test_loop_callbacks_default_to_noop(tmp_path):
    (tmp_path / "a.py").write_text("x\n")
    _run(_OneToolAdapter(), tmp_path)   # must not raise


# ── toolfmt: collapsed Claude Code-style lines ───────────────────────────────

def test_fmt_tool_start_shows_name_and_key_arg():
    line = toolfmt.fmt_tool_start("bash", {"cmd": "ls -la"})
    assert "bash" in line and "ls -la" in line and "⏺" in line


def test_fmt_tool_start_picks_path_pattern_cmd():
    assert "a.py" in toolfmt.fmt_tool_start("read", {"path": "a.py"})
    assert "TODO" in toolfmt.fmt_tool_start("grep", {"pattern": "TODO"})


def test_fmt_tool_start_truncates_long_args():
    line = toolfmt.fmt_tool_start("bash", {"cmd": "x" * 300})
    assert len(line) < 140


def test_fmt_tool_result_summarizes_lines():
    out = toolfmt.fmt_tool_result("line1\nline2\nline3")
    assert "⎿" in out and "line1" in out and "+2 lines" in out


def test_fmt_tool_result_marks_blocked():
    out = toolfmt.fmt_tool_result("[blocked] read-only mode")
    assert "blocked" in out.lower()


def test_fmt_turn_footer():
    out = toolfmt.fmt_turn_footer(seconds=12.3, tools=3, tokens=2150)
    assert "12s" in out and "3 tools" in out and "2.2k tokens" in out
    # Zero tools / small turns stay terse.
    out2 = toolfmt.fmt_turn_footer(seconds=0.8, tools=0, tokens=512)
    assert "tools" not in out2 and "512 tokens" in out2


# ── AgentSession passes the callbacks through to run_loop ───────────────────

def test_session_forwards_tool_callbacks(tmp_path):
    from ai4science.harness.session import AgentSession
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.events import TextDelta, ToolCall, Done

    (tmp_path / "a.py").write_text("x\n")
    starts, ends = [], []
    sess = AgentSession(
        adapter=StubAdapter([
            [ToolCall("c1", "read", {"path": "a.py"}), Done("tool_use")],
            [TextDelta("done"), Done("end")],
        ]),
        model="stub", backend="anthropic", workspace=tmp_path,
        read_only=True, auto_yes=False,
        on_text=lambda t: None, meter=lambda u: None,
        on_tool_start=lambda n, a: starts.append(n),
        on_tool_end=lambda n, r: ends.append(n),
    )
    sess.run_turn("read it")
    assert starts == ["read"] and ends == ["read"]


# ── REPL renders tool lines + the turn footer ────────────────────────────────

def test_repl_prints_tool_lines_and_footer(tmp_path, monkeypatch, capsys):
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.events import TextDelta, ToolCall, Done
    from ai4science.llm import routing
    import ai4science.harness.repl as repl_mod

    (tmp_path / "a.py").write_text("x = 1\n")
    stub = StubAdapter([
        [ToolCall("c1", "read", {"path": "a.py"}), Done("tool_use")],
        [TextDelta("it says x = 1"), Done("end")],
    ])
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: stub)
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: b == "anthropic")

    inputs = iter(["read a.py", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl_mod.run_common_repl(tmp_path, read_only=True, auto_yes=False,
                             backend="anthropic", model="stub")

    out = capsys.readouterr().out
    assert "⏺" in out and "read" in out          # collapsed tool-start line
    assert "⎿" in out                             # result gutter
    assert "crunched" in out and "1 tool" in out  # end-of-turn footer


def test_loop_suppresses_result_summary_for_streaming_tools(tmp_path):
    """A streaming tool already printed its output live — no `⎿` duplicate."""
    from ai4science.harness.tools.base import Registry, Tool

    def _streamer(workspace, *, cmd: str, _sink=None):
        _sink("live output\n")
        return "live output"

    reg = Registry()
    reg.add(Tool(name="bash", description="d", parameters={}, func=_streamer,
                 streams=True))

    class _BashAdapter:
        def __init__(self):
            self.n = 0
        def stream(self, history, tools, *, model, reasoning):
            self.n += 1
            if self.n == 1:
                yield ToolCall("c1", "bash", {"cmd": "ls"})
            yield Done("stop")

    ends = []
    history = [Message(role="user", content="go")]
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    loop_mod.run_loop(
        adapter=_BashAdapter(), model="stub", reasoning="low",
        history=history, workspace=tmp_path, registry=reg,
        gate=gate, on_text=lambda t: None, meter=lambda u: None,
        on_tool_end=lambda name, result: ends.append(result))
    assert ends == [""]                       # display suppressed…
    tool_msgs = [m for m in history if m.role == "tool"]
    assert tool_msgs and tool_msgs[-1].content == "live output"   # …history keeps it
