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


# ── the adapter sends a request id and cap, and keeps the platform's receipt ──

class _FakeResp:
    def __init__(self, lines):
        self.status_code = 200
        self._lines = lines
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        yield from self._lines

    def read(self):
        return b""

    def close(self):
        self.closed = True


def test_proxy_adapter_sends_request_id_and_cap_and_keeps_receipt(monkeypatch):
    import json
    import httpx
    from ai4science.harness.adapters.proxy import ProxyAdapter
    from ai4science.harness.events import TextDelta, Done
    seen = {}

    def fake_stream(method, url, json=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers)
        return _FakeResp([
            json_mod.dumps({"t": "receipt", "request_id": headers["X-Request-Id"],
                            "route": "founder-gateway", "status": "dispatched"}),
            json_mod.dumps({"t": "text", "text": "hi"}),
            json_mod.dumps({"t": "bill", "pwm": 0.5}),
            json_mod.dumps({"t": "done", "stop_reason": "end"}),
            json_mod.dumps({"t": "receipt", "request_id": headers["X-Request-Id"],
                            "status": "delivered_over_cap", "pwm_charged": 0.2,
                            "over_cap_pwm": 0.3}),
        ])

    json_mod = json
    monkeypatch.setattr(httpx, "stream", fake_stream)
    monkeypatch.setenv("AI4SCIENCE_TURN_CAP_PWM", "0.2")
    a = ProxyAdapter(backend="anthropic", base="https://x.example", token="pwm_t")
    events = list(a.stream([], [], model="m", reasoning="low"))
    assert seen["url"] == "https://x.example/api/v1/llm/proxy"
    assert seen["headers"]["X-Request-Id"] == a.last_request_id and len(a.last_request_id) >= 12
    assert seen["headers"]["X-PWM-Cap"] == "0.2"
    assert [type(e).__name__ for e in events] == ["TextDelta", "Done"]     # receipts/bill never leak as events
    assert a.last_receipt["status"] == "delivered_over_cap" and a.last_receipt["pwm_charged"] == 0.2
    # a second turn gets a fresh id and no cap when the env is unset
    monkeypatch.delenv("AI4SCIENCE_TURN_CAP_PWM")
    first = a.last_request_id
    list(a.stream([], [], model="m", reasoning="low"))
    assert a.last_request_id != first and "X-PWM-Cap" not in seen["headers"]
