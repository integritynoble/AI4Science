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


def test_proxy_adapter_sends_the_harness_session_id_when_set(monkeypatch):
    import json
    import httpx
    from ai4science.harness.adapters.proxy import ProxyAdapter
    seen = {}

    def fake_stream(method, url, json=None, headers=None, timeout=None):
        seen.update(headers=headers)
        return _FakeResp([])

    monkeypatch.setattr(httpx, "stream", fake_stream)
    a = ProxyAdapter(backend="anthropic", base="https://x.example", token="pwm_t")
    monkeypatch.delenv("AI4SCIENCE_SESSION_ID", raising=False)
    list(a.stream([], [], model="m", reasoning="low"))
    assert seen["headers"]["X-PWM-Session-Id"] == a._singleton
    monkeypatch.setenv("AI4SCIENCE_SESSION_ID", "sess-abc123")
    list(a.stream([], [], model="m", reasoning="low"))
    assert seen["headers"]["X-PWM-Session-Id"] == "sess-abc123"


def test_uncertain_dispatch_is_durable_and_blocks_restart(tmp_path, monkeypatch):
    import json
    import httpx
    import pytest
    from ai4science.harness import persistence
    from ai4science.harness.adapters.proxy import ProxyAdapter
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    monkeypatch.setenv("AI4SCIENCE_SESSION_ID", "durable")
    calls = []
    def failed(*a, **kw):
        records = json.loads(next(tmp_path.glob("proxy-*.json")).read_text())
        assert records[-1]["request_id"] == kw["headers"]["X-Request-Id"]
        assert records[-1]["status"] == "unknown"
        calls.append(kw)
        raise OSError("lost response")
    monkeypatch.setattr(httpx, "stream", failed)
    a = ProxyAdapter(backend="anthropic", base="https://x.example", token="fake")
    with pytest.raises(RuntimeError, match="lost response"):
        list(a.stream([], [], model="m"))
    fresh = ProxyAdapter(backend="openai", base="https://x.example", token="fake")
    with pytest.raises(RuntimeError, match="uncertain paid dispatch"):
        list(fresh.stream([], [], model="m"))
    assert len(calls) == 1
    class Receipt:
        def raise_for_status(self): pass
        def json(self):
            return {"request_id": a.last_request_id, "status": "delivered", "pwm_charged": .1}
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: Receipt())
    # A newly constructed adapter can reconcile immediately, before stream().
    fresh = ProxyAdapter(backend="openai", base="https://x.example", token="fake")
    fresh.reconcile_pending()
    records = json.loads(next(tmp_path.glob("proxy-*.json")).read_text())
    assert records[-1]["status"] == "settled"
    assert records[-1]["receipt"]["pwm_charged"] == .1
    assert "fake" not in next(tmp_path.glob("proxy-*.json")).read_text()


def test_checkpoint_failure_stops_before_next_tool(tmp_path):
    import pytest
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.events import ToolCall, Done
    from ai4science.harness.session import AgentSession
    from ai4science.harness.loop import CheckpointError
    from ai4science.harness.tools.base import Registry, Tool
    calls = []
    registry = Registry()
    registry.add(Tool("record", "record", {}, lambda ws: calls.append(1) or "done", mutating=False))
    adapter = StubAdapter([[ToolCall("a", "record", {}), ToolCall("b", "record", {}), Done("tool_use")]])
    def fail(): raise OSError("disk full")
    session = AgentSession(adapter=adapter, model="stub", backend="stub", workspace=tmp_path,
                           registry=registry, on_checkpoint=fail)
    with pytest.raises(CheckpointError, match="disk full"):
        session.run_turn("go")
    assert calls == [1]
    assert session.history[-1].tool_call_id == "a"


def test_repl_reconciles_saved_request_before_any_dispatch(tmp_path, monkeypatch, capsys):
    import json
    import httpx
    from ai4science.harness import persistence, repl
    from ai4science.harness.adapters.proxy import ProxyAdapter
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    monkeypatch.setenv("AI4SCIENCE_SESSION_ID", "reconcile-session")
    adapter = ProxyAdapter(backend="anthropic", base="https://x.example", token="synthetic")
    path, sid = adapter._log_path()
    persistence._atomic_write(path, json.dumps([{
        "payer": "synthetic-hash", "session": sid, "operation": "llm/proxy",
        "request_id": "saved-request", "status": "unknown", "receipt": None}]))
    calls = []
    class Receipt:
        def raise_for_status(self): pass
        def json(self):
            return {"request_id": "saved-request", "status": "delivered", "pwm_charged": .1}
    def get(*a, **kw):
        calls.append(a[0])
        return Receipt()
    monkeypatch.setattr(httpx, "get", get)
    def no_dispatch(*a, **kw):
        raise AssertionError("reconciliation must not dispatch")
    monkeypatch.setattr(httpx, "stream", no_dispatch)
    monkeypatch.setattr(repl, "adapter_for", lambda backend: adapter)
    monkeypatch.setattr(repl, "make_meter", lambda **kw: lambda u: None)
    inputs = iter(["/reconcile", "/cost", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    repl.run_common_repl(tmp_path, backend="anthropic", model="stub", session_id=sid)
    output = capsys.readouterr().out
    assert calls == ["https://x.example/api/v1/llm/receipts/saved-request"]
    assert "settled" in output and "pwm_charged" in output
    assert json.loads(path.read_text())[0]["status"] == "settled"


def test_known_payer_token_rotation_cannot_forget_pending_dispatch(tmp_path, monkeypatch):
    import httpx
    import pytest
    from ai4science import pwm_account
    from ai4science.harness import persistence
    from ai4science.harness.adapters.proxy import ProxyAdapter
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    monkeypatch.setenv("AI4SCIENCE_SESSION_ID", "rotation")
    account = {"base": "https://x.example", "token": "old-synthetic", "user_id": 123}
    monkeypatch.setattr(pwm_account, "load", lambda: account)
    calls = []
    def fail(*a, **kw):
        calls.append(1)
        raise OSError("uncertain")
    monkeypatch.setattr(httpx, "stream", fail)
    original = ProxyAdapter(backend="openai", base=account["base"], token=account["token"])
    with pytest.raises(RuntimeError):
        list(original.stream([], [], model="m"))
    account["token"] = "new-synthetic"
    rotated = ProxyAdapter(backend="openai", base=account["base"], token=account["token"])
    with pytest.raises(RuntimeError, match="uncertain paid dispatch"):
        list(rotated.stream([], [], model="m"))
    assert calls == [1]
    assert original._request_path == rotated._request_path
