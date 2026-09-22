from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.harness.adapters.anthropic import AnthropicAdapter
from ai4science.harness.events import Usage
from ai4science.llm import routing


def test_adapter_for_backend():
    assert isinstance(adapter_for("anthropic"), AnthropicAdapter)


def test_make_meter_records_to_ledger(monkeypatch):
    monkeypatch.setattr(routing, "_select_source",
                        lambda backend: ("wallet", "p1", "0xW", 1.0))
    recorded = []
    import ai4science.harness.adapters.factory as fac
    monkeypatch.setattr(fac.ledger, "record", lambda **kw: recorded.append(kw))
    meter = make_meter(backend="anthropic", model="claude-opus-4-8")
    meter(Usage(input=10, output=4, total=14))
    assert recorded and recorded[0]["model"] == "claude-opus-4-8"
    assert recorded[0]["wallet"] == "0xW"


def test_adapter_for_wires_creds(monkeypatch):
    from ai4science.harness.adapters import factory, creds
    from ai4science.harness.adapters.creds import CredInfo
    from ai4science.harness.adapters.openai import OpenAIAdapter
    from ai4science.harness.adapters.anthropic import AnthropicAdapter
    monkeypatch.setattr(creds, "resolve",
                        lambda b: CredInfo("openai_compat", "http://x/chat/completions", "k", "gpt-5.5")
                        if b == "gemini" else CredInfo("anthropic", "http://a/v1/messages", "ak", None))
    g = factory.adapter_for("gemini")
    assert isinstance(g, OpenAIAdapter) and g.creds.api_key == "k"
    a = factory.adapter_for("anthropic")
    assert isinstance(a, AnthropicAdapter) and a.creds.api_key == "ak"


def test_harness_available(monkeypatch):
    from ai4science.harness.adapters import factory, creds
    monkeypatch.setattr(creds, "available", lambda b: b == "gemini")
    # a PWM login on this machine would satisfy any backend via the founder
    # proxy; stub it so the test only exercises the local-credential path
    monkeypatch.setattr(factory, "_proxy_creds", lambda: None)
    assert factory.harness_available("gemini") is True
    assert factory.harness_available("anthropic") is False


def test_harness_available_via_proxy(monkeypatch):
    # no local credential, but the PWM route selected and a PWM login -> served
    # by the platform proxy
    from ai4science import funding
    from ai4science.harness.adapters import factory, creds
    monkeypatch.setattr(creds, "available", lambda b: False)
    monkeypatch.setattr(factory, "_proxy_creds",
                        lambda: ("pwm_k", "https://physicsworldmodel.org"))
    monkeypatch.setattr(funding, "resolve",
                        lambda: funding.Route(funding.PWM, "test", True))
    assert factory.harness_available("anthropic") is True


def test_harness_available_ignores_the_proxy_on_the_own_route(monkeypatch):
    # the same machine on the free route: a remembered PWM login adds nothing
    from ai4science import funding
    from ai4science.harness.adapters import factory, creds
    monkeypatch.setattr(creds, "available", lambda b: False)
    monkeypatch.setattr(factory, "_proxy_creds",
                        lambda: ("pwm_k", "https://physicsworldmodel.org"))
    monkeypatch.setattr(funding, "resolve",
                        lambda: funding.Route(funding.OWN, "test", False))
    assert factory.harness_available("anthropic") is False


def test_stream_no_key_guard(tmp_path):
    # an adapter with no api_key raises RuntimeError (so the fallback chain fires)
    from ai4science.harness.adapters.openai import OpenAIAdapter
    from ai4science.harness.adapters.creds import CredInfo
    import pytest
    a = OpenAIAdapter(creds=CredInfo("openai_compat", "http://x", None, "m"))
    with pytest.raises(RuntimeError, match="no API key"):
        list(a.stream([], [], model="m", reasoning="low"))
