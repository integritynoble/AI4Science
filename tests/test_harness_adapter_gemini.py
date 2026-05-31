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


def test_tool_roundtrip_preserves_real_function_name():
    """Gemini matches tool results to calls BY NAME. The ToolCall id must be the
    real function name so the loop round-trips it into functionResponse.name —
    a synthetic 'gem_<name>' id would desync the multi-turn tool loop."""
    a = GeminiAdapter()

    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    chunks = [_E(candidates=[_E(content=_E(parts=[
        _E(text=None, function_call=_E(name="read", args={"path": "a.py"}))]))],
        usage_metadata=None)]
    tc = [e for e in a._parse_stream(chunks) if isinstance(e, ToolCall)][0]
    assert tc.id == "read"   # id is the real function name, not "gem_read"

    out = a._translate_messages([Message(role="tool", content="ok", tool_call_id=tc.id)])
    assert out[0]["parts"][0]["functionResponse"]["name"] == "read"


def test_translate_user_message_with_image():
    from ai4science.harness.events import ImagePart
    a = GeminiAdapter()
    out = a._translate_messages([Message(role="user", content="what is this?",
                                         images=[ImagePart("image/png", "AAAA")])])
    parts = out[0]["parts"]
    assert any("text" in p for p in parts)
    inline = [p for p in parts if "inline_data" in p][0]["inline_data"]
    assert inline["mime_type"] == "image/png" and inline["data"] == "AAAA"
