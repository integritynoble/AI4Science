from ai4science.harness.events import TextDelta, ToolCall, Done
from ai4science.harness.adapters.openai import OpenAIAdapter
from ai4science.harness.adapters.gemini import GeminiAdapter


class _E:
    def __init__(self, **k): self.__dict__.update(k)


def test_openai_two_parallel_tool_calls():
    chunks = [
        _E(choices=[_E(delta=_E(content=None, tool_calls=[
            _E(index=0, id="c0", function=_E(name="read", arguments='{"path":"a"}')),
            _E(index=1, id="c1", function=_E(name="bash", arguments='{"cmd":"ls"}'))]),
            finish_reason="tool_calls")], usage=None),
    ]
    events = list(OpenAIAdapter()._parse_stream(chunks))
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert {t.name for t in tcs} == {"read", "bash"}
    assert {t.id for t in tcs} == {"c0", "c1"}


def test_gemini_text_then_two_calls():
    chunks = [
        _E(candidates=[_E(content=_E(parts=[
            _E(text="working ", function_call=None),
            _E(text=None, function_call=_E(name="read", args={"path": "a"})),
            _E(text=None, function_call=_E(name="glob", args={"pattern": "*.py"}))]))],
           usage_metadata=None),
    ]
    events = list(GeminiAdapter()._parse_stream(chunks))
    assert any(isinstance(e, TextDelta) for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert {t.name for t in tcs} == {"read", "glob"}
    assert sum(isinstance(e, Done) for e in events) == 1
