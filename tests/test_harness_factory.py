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
