import pytest

from ai4science.harness.adapters._dotdict import dot
from ai4science.harness.adapters.openai import OpenAIAdapter
from ai4science.harness.events import ResponseMeta


def test_openai_stream_emits_observed_metadata_before_semantic_events():
    chunks = [dot({
        "id": "chatcmpl-7",
        "model": "qwen3.8:27b",
        "system_fingerprint": "fp_ollama",
        "choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}],
    })]

    events = list(OpenAIAdapter(backend="pwm_qwen")._parse_stream(
        chunks, requested_model="qwen3.8:27b"))

    assert isinstance(events[0], ResponseMeta)
    assert sum(isinstance(event, ResponseMeta) for event in events) == 1
    meta = events[0]
    assert meta.backend == "pwm_qwen"
    assert meta.requested_model == "qwen3.8:27b"
    assert meta.observed_model == "qwen3.8:27b"
    assert meta.system_fingerprint == "fp_ollama"
    assert meta.response_id == "chatcmpl-7"
    assert meta.transport == "direct"


def test_openai_stream_keeps_absent_provider_observations_none():
    chunks = [dot({
        "choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}],
    })]

    events = list(OpenAIAdapter(backend="pwm_qwen")._parse_stream(
        chunks, requested_model="qwen3.8:27b"))

    meta = next(event for event in events if isinstance(event, ResponseMeta))
    assert meta.requested_model == "qwen3.8:27b"
    assert meta.observed_model is None
    assert meta.system_fingerprint is None
    assert meta.response_id is None


def test_openai_compat_chat_with_meta_uses_provider_response_fields(monkeypatch):
    import io
    import json

    from ai4science.llm import openai_compat

    payload = {
        "id": "chatcmpl-8",
        "model": "qwen3.8:27b",
        "system_fingerprint": "fp_ollama",
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    monkeypatch.setattr(openai_compat, "resolve_key", lambda backend: "test-key")
    monkeypatch.setattr(openai_compat, "resolve_base", lambda backend: "https://example.test/v1")
    monkeypatch.setattr(
        openai_compat.urllib.request, "urlopen",
        lambda req, timeout=0: io.BytesIO(json.dumps(payload).encode()),
    )

    text, usage, meta = openai_compat.chat_with_meta(
        "pwm_qwen", [{"role": "user", "content": "hi"}],
        model="qwen3.8:27b")

    assert text == "hello"
    assert usage["total_tokens"] == 5
    assert meta == ResponseMeta(
        backend="pwm_qwen",
        requested_model="qwen3.8:27b",
        observed_model="qwen3.8:27b",
        system_fingerprint="fp_ollama",
        response_id="chatcmpl-8",
        transport="direct",
    )


def test_openai_compat_chat_with_meta_does_not_invent_observations(monkeypatch):
    import io
    import json

    from ai4science.llm import openai_compat

    payload = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {},
    }
    monkeypatch.setattr(openai_compat, "resolve_key", lambda backend: "test-key")
    monkeypatch.setattr(openai_compat, "resolve_base", lambda backend: "https://example.test/v1")
    monkeypatch.setattr(
        openai_compat.urllib.request, "urlopen",
        lambda req, timeout=0: io.BytesIO(json.dumps(payload).encode()),
    )

    _, _, meta = openai_compat.chat_with_meta(
        "pwm_qwen", [{"role": "user", "content": "hi"}],
        model="qwen3.8:27b")

    assert meta.requested_model == "qwen3.8:27b"
    assert meta.observed_model is None
    assert meta.system_fingerprint is None
    assert meta.response_id is None


def test_factory_retains_openai_compatible_backend_name(monkeypatch):
    from ai4science.harness.adapters import creds, factory
    from ai4science.harness.adapters.creds import CredInfo

    monkeypatch.setattr(factory, "_local_available", lambda backend: True)
    monkeypatch.setattr(
        creds, "resolve",
        lambda backend: CredInfo(
            "openai_compat", "https://example.test/v1/chat/completions",
            "test-key", "qwen3.8:27b"),
    )

    adapter = factory.adapter_for("pwm_qwen")

    assert isinstance(adapter, OpenAIAdapter)
    assert adapter.backend == "pwm_qwen"


def test_openai_stream_collects_metadata_from_nonsemantic_prelude():
    chunks = [
        dot({"choices": []}),
        dot({
            "id": "chatcmpl-delayed",
            "model": "qwen3.8:27b",
            "system_fingerprint": "fp_ollama",
            "choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}],
        }),
    ]

    events = list(OpenAIAdapter(backend="pwm_qwen")._parse_stream(
        chunks, requested_model="qwen3.8:27b"))

    assert events[0] == ResponseMeta(
        "pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
        "fp_ollama", "chatcmpl-delayed", "direct")
    assert sum(isinstance(event, ResponseMeta) for event in events) == 1


def test_openai_stream_combines_partial_metadata_before_first_semantic_event():
    chunks = [
        dot({"id": "chatcmpl-partial", "choices": []}),
        dot({"model": "qwen3.8:27b", "choices": []}),
        dot({
            "system_fingerprint": "fp_ollama",
            "choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}],
        }),
    ]

    events = list(OpenAIAdapter(backend="pwm_qwen")._parse_stream(
        chunks, requested_model="qwen3.8:27b"))

    assert events[0] == ResponseMeta(
        "pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
        "fp_ollama", "chatcmpl-partial", "direct")


def test_openai_empty_stream_emits_one_none_observation_meta():
    events = list(OpenAIAdapter(backend="pwm_qwen")._parse_stream(
        iter(()), requested_model="qwen3.8:27b"))

    assert events == [ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b")]


def test_openai_pre_first_chunk_exception_exposes_meta_then_original_failure():
    class ProviderFailure(RuntimeError):
        pass

    def chunks():
        raise ProviderFailure("failed before first chunk")
        yield

    events = iter(OpenAIAdapter(backend="pwm_qwen")._parse_stream(
        chunks(), requested_model="qwen3.8:27b"))

    assert next(events) == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b")
    with pytest.raises(ProviderFailure, match="failed before first chunk"):
        next(events)


def test_openai_stream_create_failure_exposes_meta_then_original_failure(monkeypatch):
    from ai4science.harness import transport
    from ai4science.harness.adapters.creds import CredInfo

    class ProviderFailure(RuntimeError):
        pass

    def fail_create(*args, **kwargs):
        raise ProviderFailure("failed while creating stream")

    monkeypatch.setattr(transport, "sse_post", fail_create)
    adapter = OpenAIAdapter(
        creds=CredInfo("openai_compat", "https://example.test/chat/completions",
                       "test-key", "qwen3.8:27b"),
        backend="pwm_qwen",
    )
    events = iter(adapter.stream([], [], model="qwen3.8:27b", reasoning="low"))

    assert next(events) == ResponseMeta(
        backend="pwm_qwen", requested_model="qwen3.8:27b")
    with pytest.raises(ProviderFailure, match="failed while creating stream"):
        next(events)


def test_openai_missing_credential_emits_none_observation_meta_then_holds(monkeypatch):
    """Amendment 61 canonical hold: backend pwm_qwen, no credential, no proxy.

    A missing credential is a hard hold — nothing may continue on another
    model — but the base.py contract still applies: exactly one ResponseMeta,
    every provider observation None, emitted before the original exception
    propagates unchanged. A downstream strict guard decides held-vs-proven by
    inspecting the emitted ResponseMeta, so a bare raise leaves it blind.
    """
    from ai4science.harness.adapters import factory
    from ai4science.llm import openai_compat

    monkeypatch.setenv("PWM_NO_PROXY", "1")
    monkeypatch.setattr(openai_compat, "resolve_key", lambda backend: None)

    adapter = factory.adapter_for("pwm_qwen")
    assert isinstance(adapter, OpenAIAdapter)
    assert adapter.backend == "pwm_qwen"
    assert not adapter.creds.api_key

    seq = []
    with pytest.raises(RuntimeError) as excinfo:
        for event in adapter.stream([], [], model="qwen3.8:27b", reasoning="low"):
            seq.append(event)

    assert seq == [ResponseMeta(backend="pwm_qwen", requested_model="qwen3.8:27b")]
    assert type(excinfo.value) is RuntimeError
    assert str(excinfo.value) == "no API key configured for pwm_qwen backend"


def test_openai_missing_credential_meta_holds_with_no_creds_object():
    """The same hold with no CredInfo at all must not raise AttributeError
    instead of the documented precondition failure."""
    adapter = OpenAIAdapter(creds=None, backend="pwm_qwen")

    seq = []
    with pytest.raises(RuntimeError) as excinfo:
        for event in adapter.stream([], [], model="qwen3.8:27b", reasoning="low"):
            seq.append(event)

    assert seq == [ResponseMeta(backend="pwm_qwen", requested_model="qwen3.8:27b")]
    assert str(excinfo.value) == "no API key configured for pwm_qwen backend"


def test_openai_stream_module_import_failure_emits_meta_then_holds(monkeypatch):
    """The adapter's own lazy module imports must fail INSIDE the sequenced
    generator.

    `stream()` needs `transport` and `dot`. While those imports sit in the
    generator BODY they run before `_parse_stream` is ever entered, so an
    unimportable dependency produces ZERO `ResponseMeta` — the same blind-guard
    condition the missing-credential fix closed, reached by a different door.
    """
    import sys

    import ai4science.harness as harness_pkg
    from ai4science.harness.adapters.creds import CredInfo

    monkeypatch.delattr(harness_pkg, "transport", raising=False)
    monkeypatch.setitem(sys.modules, "ai4science.harness.transport", None)

    adapter = OpenAIAdapter(
        creds=CredInfo("openai_compat", "https://example.test/chat/completions",
                       "test-key", "qwen3.8:27b"),
        backend="pwm_qwen",
    )

    seq = []
    with pytest.raises(ModuleNotFoundError):
        for event in adapter.stream([], [], model="qwen3.8:27b", reasoning="low"):
            seq.append(event)

    assert seq == [ResponseMeta(backend="pwm_qwen", requested_model="qwen3.8:27b")]
