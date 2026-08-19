from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done
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


def test_parse_stream_trailing_usage_chunk_no_choices():
    # include_usage sends a final chunk with EMPTY choices carrying usage —
    # must not IndexError, and must emit a Usage event.
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    chunks = [
        _E(choices=[_E(delta=_E(content="hi", tool_calls=None), finish_reason="stop")], usage=None),
        _E(choices=[], usage=_E(prompt_tokens=11, completion_tokens=3, total_tokens=14)),
    ]
    a = OpenAIAdapter()
    events = list(a._parse_stream(chunks))
    usages = [e for e in events if isinstance(e, Usage)]
    assert usages and usages[-1].total == 14
    assert any(isinstance(e, Done) for e in events)


def test_translate_user_message_with_image():
    from ai4science.harness.events import Message, ImagePart
    a = OpenAIAdapter()
    out = a._translate_messages([Message(role="user", content="what is this?",
                                         images=[ImagePart("image/png", "AAAA")])])
    content = out[0]["content"]
    assert any(b.get("type") == "text" for b in content)
    img = [b for b in content if b.get("type") == "image_url"][0]
    assert img["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_openai_stream_sse_endtoend(monkeypatch):
    from ai4science.harness.adapters.openai import OpenAIAdapter
    from ai4science.harness.adapters.creds import CredInfo
    from ai4science.harness import transport
    from ai4science.harness.events import TextDelta, Done
    a = OpenAIAdapter(creds=CredInfo("openai_compat", "http://x/chat/completions", "k", "gpt-5.5"))
    sse = [{"choices": [{"delta": {"content": "hi"}, "finish_reason": None}], "usage": None},
           {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5}}]
    captured = {}
    def _fake_sse(url, headers, payload, timeout=600):
        captured["url"] = url; captured["headers"] = headers; captured["payload"] = payload
        return iter(sse)
    monkeypatch.setattr(transport, "sse_post", _fake_sse)
    events = list(a.stream([], [], model="gpt-5.5", reasoning="low"))
    assert any(isinstance(e, TextDelta) for e in events)
    assert any(isinstance(e, Done) for e in events)
    # the request was built correctly
    assert captured["url"] == "http://x/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["payload"]["stream"] is True and captured["payload"]["model"] == "gpt-5.5"


def test_openai_tool_call_extra_signature_roundtrip():
    """Gemini's OpenAI-compat tool calls carry extra_content.thought_signature that
    MUST be captured on parse and echoed back on translate, or the next request 400s."""
    from ai4science.harness.adapters.openai import OpenAIAdapter
    from ai4science.harness.adapters._dotdict import dot
    from ai4science.harness.events import Message, ToolCall
    a = OpenAIAdapter()
    chunk = dot({"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": "c0",
         "extra_content": {"google": {"thought_signature": "SIG"}},
         "function": {"name": "read", "arguments": "{\"path\": \"a\"}"}}]},
        "finish_reason": "tool_calls"}]})
    tcs = [e for e in a._parse_stream(iter([chunk])) if isinstance(e, ToolCall)]
    assert tcs and tcs[0].extra == {"google": {"thought_signature": "SIG"}}
    out = a._translate_messages([Message(role="assistant", content="", tool_calls=[
        ToolCall("c0", "read", {"path": "a"}, extra={"google": {"thought_signature": "SIG"}})])])
    assert out[0]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "SIG"}}


# ── backend plumbing + ResponseMeta emission ───────────────────────────────
def _is_meta(e):
    # identify ResponseMeta without importing it (so RED fails on the missing
    # FEATURE — an unemitted event — not on a module-level import error)
    return type(e).__name__ == "ResponseMeta"


def _adapter(backend="pwm_qwen"):
    from ai4science.harness.adapters.openai import OpenAIAdapter
    from ai4science.harness.adapters.creds import CredInfo
    return OpenAIAdapter(creds=CredInfo("openai_compat",
                                        "http://x/chat/completions", "k", "m"),
                         backend=backend)


def _run_stream(adapter, monkeypatch, sse_iter):
    from ai4science.harness import transport
    monkeypatch.setattr(transport, "sse_post",
                        lambda url, headers, payload, timeout=600: sse_iter)
    return list(adapter.stream([], [], model="req-model", reasoning="low"))


def test_adapter_accepts_and_reports_backend():
    from ai4science.harness.adapters.openai import OpenAIAdapter
    assert OpenAIAdapter(backend="pwm_qwen").backend == "pwm_qwen"
    assert OpenAIAdapter().backend == "openai"        # class default preserved


def test_stream_emits_single_responsemeta_before_semantic(monkeypatch):
    a = _adapter()
    sse = iter([
        {"id": "resp-1", "model": "qwen3.8:27b-observed",
         "system_fingerprint": "fp-9",
         "choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}},
    ])
    events = _run_stream(a, monkeypatch, sse)
    metas = [e for e in events if _is_meta(e)]
    assert len(metas) == 1                            # EXACTLY one
    assert events[0] is metas[0]                      # BEFORE every semantic event
    assert len(events) > 1                            # there ARE semantic events
    m = metas[0]
    assert m.backend == "pwm_qwen"
    assert m.requested_model == "req-model"
    assert m.observed_model == "qwen3.8:27b-observed"
    assert m.system_fingerprint == "fp-9"
    assert m.response_id == "resp-1"
    assert m.transport == "sse"
    # observed must come from the provider, never manufactured from the request
    assert m.observed_model != m.requested_model


def test_stream_responsemeta_none_when_provider_metadata_absent(monkeypatch):
    # NEGATIVE FIXTURE 1: chunk with no id/model/system_fingerprint
    a = _adapter()
    sse = iter([{"choices": [{"delta": {"content": "hi"}, "finish_reason": "stop"}]}])
    events = _run_stream(a, monkeypatch, sse)
    metas = [e for e in events if _is_meta(e)]
    assert len(metas) == 1
    m = metas[0]
    assert m.observed_model is None
    assert m.system_fingerprint is None
    assert m.response_id is None
    assert m.requested_model == "req-model"           # request side still recorded


def test_stream_empty_still_emits_one_responsemeta(monkeypatch):
    # NEGATIVE FIXTURE 2: empty stream -> still exactly one ResponseMeta
    a = _adapter()
    events = _run_stream(a, monkeypatch, iter([]))
    metas = [e for e in events if _is_meta(e)]
    assert len(metas) == 1
    assert events == metas                            # nothing but the meta
    m = metas[0]
    assert m.observed_model is None
    assert m.system_fingerprint is None
    assert m.response_id is None


def test_stream_error_before_first_chunk_emits_meta_then_reraises(monkeypatch):
    # NEGATIVE FIXTURE 3: pre-chunk failure -> one ResponseMeta, then the
    # ORIGINAL exception (type AND message), not a wrapper
    import pytest
    from ai4science.harness import transport

    class Boom(RuntimeError):
        pass

    def _raising():
        raise Boom("kaboom-original")
        yield  # pragma: no cover  (make this a generator)

    a = _adapter()
    monkeypatch.setattr(transport, "sse_post",
                        lambda url, headers, payload, timeout=600: _raising())
    collected = []
    with pytest.raises(Boom) as ei:
        for e in a.stream([], [], model="req-model", reasoning="low"):
            collected.append(e)
    assert str(ei.value) == "kaboom-original"         # original message, unwrapped
    metas = [e for e in collected if _is_meta(e)]
    assert len(metas) == 1
    assert collected[0] is metas[0]                   # meta emitted before the raise


# ── delayed metadata: accumulate across prelude chunks, emit once ───────────
def test_stream_meta_from_empty_prelude_then_metadata_chunk(monkeypatch):
    # The FIRST chunk is an empty prelude ({"choices": []}) that carries NO
    # provider fields; id/model/system_fingerprint all arrive on the SECOND
    # chunk. Reading only the first chunk loses them — the one ResponseMeta
    # must still report all three.
    a = _adapter()
    sse = iter([
        {"choices": []},
        {"id": "resp-2", "model": "qwen3.8:27b-observed",
         "system_fingerprint": "fp-7",
         "choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ])
    events = _run_stream(a, monkeypatch, sse)
    metas = [e for e in events if _is_meta(e)]
    assert len(metas) == 1                             # EXACTLY one
    assert events[0] is metas[0]                       # BEFORE every semantic event
    assert len(events) > 1                             # there ARE semantic events
    m = metas[0]
    assert m.response_id == "resp-2"
    assert m.observed_model == "qwen3.8:27b-observed"
    assert m.system_fingerprint == "fp-7"
    assert m.observed_model != m.requested_model       # never copied from request


def test_stream_meta_accumulates_fields_split_across_three_chunks(monkeypatch):
    # id, model and system_fingerprint each arrive on a DIFFERENT prelude chunk;
    # each is filled the first time it appears. A later chunk supplies a field an
    # earlier chunk lacked. The single emitted meta carries all three, and is
    # emitted immediately before the first semantic event (the text chunk).
    a = _adapter()
    sse = iter([
        {"id": "resp-3", "choices": []},
        {"model": "qwen3.8:27b-observed", "choices": []},
        {"system_fingerprint": "fp-5", "choices": []},
        {"choices": [{"delta": {"content": "hi"}, "finish_reason": "stop"}]},
    ])
    events = _run_stream(a, monkeypatch, sse)
    metas = [e for e in events if _is_meta(e)]
    assert len(metas) == 1
    assert events[0] is metas[0]                       # precedes every semantic event
    assert len(events) > 1
    m = metas[0]
    assert m.response_id == "resp-3"
    assert m.observed_model == "qwen3.8:27b-observed"
    assert m.system_fingerprint == "fp-5"
    assert m.observed_model != m.requested_model


def test_stream_meta_stays_none_across_chunks_without_provider_fields(monkeypatch):
    # NEGATIVE: multiple chunks, none carrying id/model/system_fingerprint —
    # observed fields must never be manufactured from the request even after
    # accumulating across the whole stream.
    a = _adapter()
    sse = iter([
        {"choices": [{"delta": {"content": "hi "}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "there"}, "finish_reason": "stop"}]},
    ])
    events = _run_stream(a, monkeypatch, sse)
    metas = [e for e in events if _is_meta(e)]
    assert len(metas) == 1
    assert events[0] is metas[0]
    m = metas[0]
    assert m.observed_model is None
    assert m.system_fingerprint is None
    assert m.response_id is None
    assert m.requested_model == "req-model"            # request side still recorded
