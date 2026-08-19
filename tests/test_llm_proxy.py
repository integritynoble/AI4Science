"""LLM proxy wire protocol + factory proxy selection."""
import json

import pytest

from ai4science.harness import proxy_proto as proto
from ai4science.harness.events import (Done, Message, ResponseMeta, TextDelta,
                                        ToolCall, ToolSpec, Usage)


def test_message_roundtrip():
    m = Message(role="assistant", content="hi",
                tool_calls=[ToolCall(id="t1", name="Bash", arguments={"command": "ls"})])
    out = proto.msg_from_wire(proto.msg_to_wire(m))
    assert out.role == "assistant" and out.content == "hi"
    assert out.tool_calls[0].name == "Bash" and out.tool_calls[0].arguments == {"command": "ls"}


def test_tool_roundtrip():
    t = ToolSpec(name="Read", description="read a file", parameters={"type": "object"})
    out = proto.tool_from_wire(proto.tool_to_wire(t))
    assert out.name == "Read" and out.parameters == {"type": "object"}


def test_event_roundtrip():
    for ev, kind in [(TextDelta("x"), TextDelta), (ToolCall("i", "n", {}), ToolCall),
                     (Usage(input=10, output=5), Usage), (Done("end"), Done)]:
        back = proto.event_from_wire(proto.event_to_wire(ev))
        assert isinstance(back, kind)


def test_factory_picks_proxy_when_no_local_cred(monkeypatch, tmp_path):
    monkeypatch.setenv("AI4SCIENCE_PWM_ACCOUNT", str(tmp_path / "a.json"))
    monkeypatch.setenv("PWM_TOKEN", "pwm_x")
    monkeypatch.setenv("PWM_BASE", "https://mirror.example")
    from ai4science.harness.adapters import factory
    monkeypatch.setattr(factory, "_local_available", lambda b: False)
    a = factory.adapter_for("anthropic")
    assert type(a).__name__ == "ProxyAdapter" and a.base == "https://mirror.example"


def test_factory_prefers_local_when_available(monkeypatch):
    monkeypatch.setenv("PWM_TOKEN", "pwm_x")
    from ai4science.harness.adapters import factory
    monkeypatch.setattr(factory, "_local_available", lambda b: True)
    a = factory.adapter_for("anthropic")
    assert type(a).__name__ != "ProxyAdapter"   # local wins


def test_response_metadata_round_trips_over_proxy():
    source = ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
                          "fp_ollama", "chatcmpl-7", "gateway")

    assert proto.event_from_wire(proto.event_to_wire(source)) == source


def test_proxy_adapter_marks_observed_metadata_as_proxy(monkeypatch):
    import httpx

    from ai4science.harness.adapters.proxy import ProxyAdapter

    source = ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
                          "fp_ollama", "chatcmpl-7", "gateway")

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def close(self):
            pass

        def iter_lines(self):
            yield json.dumps(proto.event_to_wire(source))

    monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: Response())

    events = list(ProxyAdapter(
        backend="requested-alias", base="https://proxy.test", token="test-token",
    ).stream([], [], model="requested-model"))

    assert events == [ResponseMeta(
        backend="pwm_qwen",
        requested_model="qwen3.8:27b",
        observed_model="qwen3.8:27b",
        system_fingerprint="fp_ollama",
        response_id="chatcmpl-7",
        transport="proxy",
    )]


def test_proxy_cannot_invent_missing_provider_observations(monkeypatch):
    import httpx

    from ai4science.harness.adapters.proxy import ProxyAdapter

    source = ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b", transport="gateway")

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def close(self):
            pass

        def iter_lines(self):
            yield json.dumps(proto.event_to_wire(source))

    monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: Response())

    meta = next(iter(ProxyAdapter(
        backend="pwm_qwen", base="https://proxy.test", token="test-token",
    ).stream([], [], model="qwen3.8:27b")))

    assert isinstance(meta, ResponseMeta)
    assert meta.requested_model == "qwen3.8:27b"
    assert meta.observed_model is None
    assert meta.system_fingerprint is None
    assert meta.response_id is None
    assert meta.transport == "proxy"


def test_gateway_health_includes_pwm_qwen(monkeypatch):
    from ai4science.harness import llm_gateway

    monkeypatch.setattr(llm_gateway, "harness_available", lambda backend: True)

    assert llm_gateway.health()["backends"]["pwm_qwen"] is True


def test_gateway_stream_forwards_metadata_unchanged(monkeypatch):
    import asyncio

    from ai4science.harness import llm_gateway

    source = ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
                          "fp_ollama", "chatcmpl-7", "direct")

    class Adapter:
        def stream(self, messages, tools, *, model, reasoning):
            yield source

    monkeypatch.setattr(llm_gateway, "TOKEN", "gateway-token")
    monkeypatch.setattr(llm_gateway, "harness_available", lambda backend: True)
    monkeypatch.setattr(llm_gateway, "adapter_for", lambda backend: Adapter())
    monkeypatch.setattr(llm_gateway.pricing, "price_call", lambda model, usage: {"pwm": 0})
    monkeypatch.setattr(
        llm_gateway.routing, "_select_source",
        lambda backend: ("wallet", "provider", "0xtest", 1.0),
    )

    response = llm_gateway.stream(
        llm_gateway.StreamReq(
            backend="pwm_qwen", model="qwen3.8:27b", messages=[]),
        x_bridge_token="gateway-token",
    )

    async def collect():
        return [chunk async for chunk in response.body_iterator]

    lines = asyncio.run(collect())
    first = lines[0].decode() if isinstance(lines[0], bytes) else lines[0]
    forwarded = proto.event_from_wire(json.loads(first))

    assert forwarded == source


def _proxy_stream_from_lines(monkeypatch, lines):
    import httpx

    from ai4science.harness.adapters.proxy import ProxyAdapter

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def close(self):
            pass

        def iter_lines(self):
            yield from lines

    monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: Response())
    return iter(ProxyAdapter(
        backend="pwm_qwen", base="https://proxy.test", token="test-token",
    ).stream([], [], model="qwen3.8:27b"))


def test_proxy_duplicate_metadata_yields_one_then_fails_closed(monkeypatch):
    source = ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
                          "fp_ollama", "chatcmpl-7", "gateway")
    line = json.dumps(proto.event_to_wire(source))
    events = _proxy_stream_from_lines(monkeypatch, [line, line])

    assert next(events).transport == "proxy"
    with pytest.raises(RuntimeError, match="duplicate metadata"):
        next(events)


def test_proxy_text_before_metadata_exposes_none_meta_then_fails_closed(monkeypatch):
    lines = [
        json.dumps(proto.event_to_wire(TextDelta("too early"))),
        json.dumps(proto.event_to_wire(ResponseMeta(
            "pwm_qwen", "qwen3.8:27b", "qwen3.8:27b"))),
    ]
    events = _proxy_stream_from_lines(monkeypatch, lines)

    meta = next(events)
    assert meta == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b", transport="proxy")
    with pytest.raises(RuntimeError, match="semantic event before metadata"):
        next(events)


def test_proxy_malformed_metadata_exposes_none_meta_then_fails_closed(monkeypatch):
    malformed = {
        "t": "meta",
        "backend": "pwm_qwen",
        "requested_model": "qwen3.8:27b",
        "transport": "gateway",
    }
    events = _proxy_stream_from_lines(monkeypatch, [json.dumps(malformed)])

    meta = next(events)
    assert meta.observed_model is None
    assert meta.system_fingerprint is None
    assert meta.response_id is None
    with pytest.raises(RuntimeError, match="malformed metadata"):
        next(events)


def test_proxy_empty_stream_exposes_none_meta_then_fails_closed(monkeypatch):
    events = _proxy_stream_from_lines(monkeypatch, [])

    assert next(events) == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b", transport="proxy")
    with pytest.raises(RuntimeError, match="ended without valid metadata"):
        next(events)


def test_proxy_clean_termination_after_valid_metadata_is_accepted(monkeypatch):
    source = ResponseMeta("server_backend", "server-requested", None, None, None,
                          "gateway")
    events = list(_proxy_stream_from_lines(
        monkeypatch, [json.dumps(proto.event_to_wire(source))]))

    assert events == [ResponseMeta(
        "server_backend", "server-requested", None, None, None, "proxy")]


def test_gateway_pre_meta_failure_emits_none_meta_before_error_semantics(monkeypatch):
    import asyncio

    from ai4science.harness import llm_gateway

    class ProviderFailure(RuntimeError):
        pass

    class Adapter:
        def stream(self, messages, tools, *, model, reasoning):
            raise ProviderFailure("upstream failed before metadata")

    monkeypatch.setattr(llm_gateway, "TOKEN", "gateway-token")
    monkeypatch.setattr(llm_gateway, "harness_available", lambda backend: True)
    monkeypatch.setattr(llm_gateway, "adapter_for", lambda backend: Adapter())
    monkeypatch.setattr(llm_gateway.pricing, "price_call", lambda model, usage: {"pwm": 0})
    monkeypatch.setattr(
        llm_gateway.routing, "_select_source",
        lambda backend: ("wallet", "provider", "0xtest", 1.0),
    )
    response = llm_gateway.stream(
        llm_gateway.StreamReq(
            backend="pwm_qwen", model="qwen3.8:27b", messages=[]),
        x_bridge_token="gateway-token",
    )

    async def collect():
        return [chunk async for chunk in response.body_iterator]

    raw_lines = asyncio.run(collect())
    wires = [json.loads(line.decode() if isinstance(line, bytes) else line)
             for line in raw_lines]

    assert [wire["t"] for wire in wires] == ["meta", "text", "done", "bill"]
    meta = proto.event_from_wire(wires[0])
    assert meta == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b")


def test_gateway_empty_adapter_emits_none_meta_before_bill(monkeypatch):
    import asyncio

    from ai4science.harness import llm_gateway

    class Adapter:
        def stream(self, messages, tools, *, model, reasoning):
            return iter(())

    monkeypatch.setattr(llm_gateway, "TOKEN", "gateway-token")
    monkeypatch.setattr(llm_gateway, "harness_available", lambda backend: True)
    monkeypatch.setattr(llm_gateway, "adapter_for", lambda backend: Adapter())
    monkeypatch.setattr(llm_gateway.pricing, "price_call", lambda model, usage: {"pwm": 0})
    monkeypatch.setattr(
        llm_gateway.routing, "_select_source",
        lambda backend: ("wallet", "provider", "0xtest", 1.0),
    )
    response = llm_gateway.stream(
        llm_gateway.StreamReq(
            backend="pwm_qwen", model="qwen3.8:27b", messages=[]),
        x_bridge_token="gateway-token",
    )

    async def collect():
        return [chunk async for chunk in response.body_iterator]

    raw_lines = asyncio.run(collect())
    wires = [json.loads(line.decode() if isinstance(line, bytes) else line)
             for line in raw_lines]

    assert [wire["t"] for wire in wires] == ["meta", "bill"]
    assert proto.event_from_wire(wires[0]) == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b")


def test_proxy_non_json_line_exposes_none_meta_then_fails_closed(monkeypatch):
    """A line that is not JSON must fail the stream closed, not be skipped.

    The second line is a VALID metadata event: if the malformed-JSON guard were
    replaced by a silent `continue`, the stream would recover and release real
    server evidence, so this fixture distinguishes fail-closed from skip.
    """
    valid = ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
                         "fp_ollama", "chatcmpl-7", "gateway")
    events = _proxy_stream_from_lines(
        monkeypatch, ["this is not json", json.dumps(proto.event_to_wire(valid))])

    assert next(events) == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b", transport="proxy")
    with pytest.raises(RuntimeError, match="invalid JSON"):
        next(events)


def test_proxy_bill_before_metadata_exposes_none_meta_then_fails_closed(monkeypatch):
    """A billing line before metadata means the turn was charged with the route
    still unproven — fail closed there, do not read on.

    The second line is a VALID metadata event, so dropping the guard would let
    the stream recover and release real server evidence.
    """
    valid = ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
                         "fp_ollama", "chatcmpl-7", "gateway")
    events = _proxy_stream_from_lines(
        monkeypatch, [json.dumps({"t": "bill"}),
                      json.dumps(proto.event_to_wire(valid))])

    assert next(events) == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b", transport="proxy")
    with pytest.raises(RuntimeError, match="ended without valid metadata"):
        next(events)


def test_gateway_no_metadata_adapter_emits_meta_before_first_semantic_event(monkeypatch):
    """The MID-STREAM fallback emit is load-bearing, not defensive.

    `adapters/base.py:15` requires one `ResponseMeta` before any semantic event,
    but only `openai.py` and `proxy.py` emit one. `anthropic.py`, `gemini.py`,
    `codex.py` and `stub.py` do not — four of the six shipped adapters — and
    `health()` advertises `anthropic` and `gemini`. For those backends the FIRST
    semantic event of EVERY request reaches the mid-stream emit in `_gen`, so
    dropping or reordering it puts the metadata line AFTER the semantics on the
    wire and every gateway-routed session dies on its first token with
    "proxy semantic event before metadata".

    The two existing gateway fixtures cover the empty-stream and exception
    sites; neither reaches the mid-stream one. This drives the real generator
    with a no-metadata adapter and then feeds its EXACT bytes to the real
    `ProxyAdapter`, so the assertion is the client's, not a restatement of the
    server's code. No network.
    """
    import asyncio

    import httpx

    from ai4science.harness import llm_gateway
    from ai4science.harness.adapters.proxy import ProxyAdapter

    class NoMetadataAdapter:
        """The shape of anthropic.py / gemini.py / codex.py / stub.py today."""

        def stream(self, messages, tools, *, model, reasoning):
            yield TextDelta("hello")
            yield ToolCall(id="call-1", name="bash", arguments={"cmd": "ls"})
            yield Usage(input=3, output=5)
            yield Done(stop_reason="end_turn")

    monkeypatch.setattr(llm_gateway, "TOKEN", "gateway-token")
    monkeypatch.setattr(llm_gateway, "harness_available", lambda backend: True)
    monkeypatch.setattr(llm_gateway, "adapter_for",
                        lambda backend: NoMetadataAdapter())
    monkeypatch.setattr(llm_gateway.pricing, "price_call",
                        lambda model, usage: {"pwm": 0})
    monkeypatch.setattr(
        llm_gateway.routing, "_select_source",
        lambda backend: ("wallet", "provider", "0xtest", 1.0),
    )

    response = llm_gateway.stream(
        llm_gateway.StreamReq(
            backend="anthropic", model="claude-opus-5", messages=[]),
        x_bridge_token="gateway-token",
    )

    async def collect():
        return [chunk async for chunk in response.body_iterator]

    lines = [chunk.decode() if isinstance(chunk, bytes) else chunk
             for chunk in asyncio.run(collect())]
    kinds = [json.loads(line)["t"] for line in lines]

    assert kinds[0] == "meta", (
        f"metadata must precede every semantic event; wire was {kinds}")
    assert kinds == ["meta", "text", "tool", "usage", "done", "bill"]
    assert proto.event_from_wire(json.loads(lines[0])) == ResponseMeta(
        backend="anthropic", requested_model="claude-opus-5")

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def close(self):
            pass

        def iter_lines(self):
            yield from [line.rstrip("\n") for line in lines]

    monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: Response())
    received = list(ProxyAdapter(
        backend="anthropic", base="https://proxy.test", token="test-token",
    ).stream([], [], model="claude-opus-5"))

    assert [type(event).__name__ for event in received] == [
        "ResponseMeta", "TextDelta", "ToolCall", "Usage", "Done"]
