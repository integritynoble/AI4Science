from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Done
from ai4science.harness.adapters.openai import OpenAIAdapter


def test_translate_tools_function_schema():
    a = OpenAIAdapter()
    out = a._translate_tools([ToolSpec("bash", "run", {"type": "object", "properties": {"cmd": {"type": "string"}}})])
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "bash"


def test_translate_messages_tool_result():
    a = OpenAIAdapter()
    msgs = [
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "bash", {"cmd": "ls"})]),
        Message(role="tool", content="a.py", tool_call_id="c1"),
    ]
    out = a._translate_messages(msgs)
    assert out[0]["tool_calls"][0]["id"] == "c1"
    assert out[1]["role"] == "tool" and out[1]["tool_call_id"] == "c1"


def test_parse_stream_collects_tool_call_deltas():
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    chunks = [
        _E(choices=[_E(delta=_E(content="ok ", tool_calls=None), finish_reason=None)], usage=None),
        _E(choices=[_E(delta=_E(content=None, tool_calls=[
            _E(index=0, id="c1", function=_E(name="bash", arguments='{"cmd":'))]), finish_reason=None)], usage=None),
        _E(choices=[_E(delta=_E(content=None, tool_calls=[
            _E(index=0, id=None, function=_E(name=None, arguments=' "ls"}'))]), finish_reason="tool_calls")], usage=None),
    ]
    a = OpenAIAdapter()
    events = list(a._parse_stream(chunks))
    assert any(isinstance(e, TextDelta) for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert tcs and tcs[0].name == "bash" and tcs[0].arguments == {"cmd": "ls"}
    assert any(isinstance(e, Done) for e in events)
