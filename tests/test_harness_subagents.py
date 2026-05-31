from pathlib import Path
from ai4science.harness.subagents import SUBAGENTS, make_task_tool
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done


def test_subagents_registry_has_profiles():
    assert "general" in SUBAGENTS
    assert "system_prompt" in SUBAGENTS["general"]


def test_task_tool_runs_nested_session(tmp_path):
    def _factory(*, subagent_type, depth):
        from ai4science.harness.session import AgentSession
        return AgentSession(
            adapter=StubAdapter([[TextDelta("child-done"), Done("end")]]),
            model="stub", backend="anthropic", workspace=tmp_path,
            read_only=False, auto_yes=True, on_text=lambda t: None, meter=lambda u: None,
        )
    tool = make_task_tool(session_factory=_factory, depth=0, max_depth=2)
    assert tool.name == "task"
    out = tool.func(tmp_path, subagent_type="general", prompt="do a thing")
    assert "child-done" in out


def test_task_tool_depth_guard(tmp_path):
    tool = make_task_tool(session_factory=lambda **k: None, depth=2, max_depth=2)
    out = tool.func(tmp_path, subagent_type="general", prompt="x")
    assert "depth" in out.lower() and "max" in out.lower()


def test_task_tool_unknown_subagent(tmp_path):
    tool = make_task_tool(session_factory=lambda **k: None, depth=0, max_depth=2)
    out = tool.func(tmp_path, subagent_type="nope", prompt="x")
    assert "unknown" in out.lower()
