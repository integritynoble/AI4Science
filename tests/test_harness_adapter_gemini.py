from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Done
from ai4science.harness.adapters.gemini import GeminiAdapter


def test_translate_tools_function_declarations():
    a = GeminiAdapter()
    out = a._translate_tools([ToolSpec("read", "r", {"type": "object", "properties": {"path": {"type": "string"}}})])
    assert out[0]["function_declarations"][0]["name"] == "read"


def test_translate_messages_contents_roles():
    a = GeminiAdapter()
    msgs = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "read", {"path": "a"})]),
        Message(role="tool", content="data", tool_call_id="c1"),
    ]
    out = a._translate_messages(msgs)
    assert out[0]["role"] == "user"
    assert out[1]["role"] == "model"
    assert any("functionCall" in p for p in out[1]["parts"])
    assert out[2]["role"] == "function"


def test_parse_stream_text_and_function_call():
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    chunks = [
        _E(candidates=[_E(content=_E(parts=[_E(text="hi ", function_call=None)]))], usage_metadata=None),
        _E(candidates=[_E(content=_E(parts=[
            _E(text=None, function_call=_E(name="read", args={"path": "a.py"}))]))],
           usage_metadata=_E(prompt_token_count=4, candidates_token_count=3, total_token_count=7)),
    ]
    a = GeminiAdapter()
    events = list(a._parse_stream(chunks))
    assert any(isinstance(e, TextDelta) for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert tcs and tcs[0].name == "read" and tcs[0].arguments == {"path": "a.py"}
    assert any(isinstance(e, Done) for e in events)
