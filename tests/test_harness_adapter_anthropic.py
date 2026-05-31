from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done
from ai4science.harness.adapters.anthropic import AnthropicAdapter


def test_translate_tools_to_anthropic_schema():
    a = AnthropicAdapter()
    specs = [ToolSpec("read", "read a file", {"type": "object", "properties": {"path": {"type": "string"}}})]
    out = a._translate_tools(specs)
    assert out[0]["name"] == "read"
    assert out[0]["input_schema"]["properties"]["path"]["type"] == "string"


def test_translate_messages_roles():
    a = AnthropicAdapter()
    msgs = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="reading", tool_calls=[ToolCall("c1", "read", {"path": "a"})]),
        Message(role="tool", content="contents", tool_call_id="c1"),
    ]
    out = a._translate_messages(msgs)
    assert out[0]["role"] == "user"
    assert any(b.get("type") == "tool_use" for b in out[1]["content"])
    assert out[2]["role"] == "user"
    assert any(b.get("type") == "tool_result" for b in out[2]["content"])


def test_parse_stream_events():
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    raw = [
        _E(type="content_block_delta", delta=_E(type="text_delta", text="Hello")),
        _E(type="content_block_start", content_block=_E(type="tool_use", id="c1", name="read", input={})),
        _E(type="content_block_delta", delta=_E(type="input_json_delta", partial_json='{"path": "a.py"}')),
        _E(type="content_block_stop"),
        _E(type="message_delta", usage=_E(output_tokens=5), delta=_E(stop_reason="tool_use")),
        _E(type="message_stop"),
    ]
    a = AnthropicAdapter()
    events = list(a._parse_stream(raw, input_tokens=10))
    assert any(isinstance(e, TextDelta) and e.text == "Hello" for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert tcs and tcs[0].name == "read" and tcs[0].arguments == {"path": "a.py"}
    assert any(isinstance(e, Usage) for e in events)
    assert any(isinstance(e, Done) for e in events)


def test_parse_stream_captures_input_tokens_from_message_start():
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    raw = [
        _E(type="message_start", message=_E(usage=_E(input_tokens=42))),
        _E(type="content_block_delta", delta=_E(type="text_delta", text="hi")),
        _E(type="message_delta", usage=_E(output_tokens=5), delta=_E(stop_reason="end_turn")),
        _E(type="message_stop"),
    ]
    a = AnthropicAdapter()
    usages = [e for e in a._parse_stream(raw) if isinstance(e, Usage)]
    assert usages and usages[0].input == 42 and usages[0].output == 5
    assert usages[0].total == 47


def test_translate_user_message_with_image():
    from ai4science.harness.events import ImagePart
    a = AnthropicAdapter()
    msgs = [Message(role="user", content="what is this?",
                    images=[ImagePart("image/png", "AAAA")])]
    out = a._translate_messages(msgs)
    blocks = out[0]["content"]
    assert any(b.get("type") == "text" for b in blocks)
    img = [b for b in blocks if b.get("type") == "image"][0]
    assert img["source"]["type"] == "base64"
    assert img["source"]["media_type"] == "image/png" and img["source"]["data"] == "AAAA"
