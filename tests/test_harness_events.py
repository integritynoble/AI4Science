from ai4science.harness.events import (
    Message, ToolSpec, TextDelta, ToolCall, Usage, Done,
)


def test_message_roundtrip():
    m = Message(role="user", content="hello")
    assert m.role == "user" and m.content == "hello"
    assert m.tool_calls == [] and m.tool_call_id is None


def test_tool_spec_fields():
    t = ToolSpec(name="read", description="read a file",
                 parameters={"type": "object", "properties": {"path": {"type": "string"}}})
    assert t.name == "read"
    assert t.parameters["properties"]["path"]["type"] == "string"


def test_event_variants():
    assert TextDelta(text="hi").text == "hi"
    tc = ToolCall(id="c1", name="bash", arguments={"cmd": "ls"})
    assert tc.name == "bash" and tc.arguments["cmd"] == "ls"
    assert Usage(input=10, output=5, total=15).total == 15
    assert isinstance(Done(), Done)
