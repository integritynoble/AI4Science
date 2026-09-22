"""LLM proxy wire protocol + factory proxy selection."""
from ai4science.harness import proxy_proto as proto
from ai4science.harness.events import Message, ToolCall, ToolSpec, TextDelta, Usage, Done


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
    # A token and no credential of the user's own anywhere: the PWM route is
    # the only one that can serve, so the proxy does. (With an own credential
    # it would be the free route and never the proxy — tests/test_funding_route.py.)
    monkeypatch.setenv("AI4SCIENCE_PWM_ACCOUNT", str(tmp_path / "a.json"))
    monkeypatch.setenv("AI4SCIENCE_USER_CONFIG", str(tmp_path / "user.json"))
    monkeypatch.setenv("AI4SCIENCE_KEYS", str(tmp_path / "keys.json"))
    monkeypatch.delenv("AI4SCIENCE_FUNDING", raising=False)
    monkeypatch.delenv("AI4SCIENCE_PWM_GATE", raising=False)
    monkeypatch.setenv("PWM_TOKEN", "pwm_x")
    monkeypatch.setenv("PWM_BASE", "https://mirror.example")
    from ai4science.harness.adapters import factory, creds
    monkeypatch.setattr(creds, "available", lambda b: False)
    monkeypatch.setattr(factory, "_local_available", lambda b: False)
    a = factory.adapter_for("anthropic")
    assert type(a).__name__ == "ProxyAdapter" and a.base == "https://mirror.example"


def test_factory_prefers_local_when_available(monkeypatch):
    monkeypatch.setenv("PWM_TOKEN", "pwm_x")
    from ai4science.harness.adapters import factory
    monkeypatch.setattr(factory, "_local_available", lambda b: True)
    a = factory.adapter_for("anthropic")
    assert type(a).__name__ != "ProxyAdapter"   # local wins
