"""E1 AI4Science hook — PwmGate.post_usage + cassi_dispatch usage logging."""
from ai4science.harness.pwm_gate import PwmGate
from ai4science import wallet


# ── PwmGate.post_usage ───────────────────────────────────────────────────
def test_post_usage_off_is_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(wallet, "http_post", lambda *a, **k: (calls.append(a), (200, {}))[1])
    g = PwmGate(token=None, base="http://x", enabled=False)
    assert g.post_usage(contribution_id="c1", agent_name="computational-imaging",
                        turn_id="t1") is False
    assert calls == []                          # gate off → no HTTP


def test_post_usage_on_posts_to_agent_pool(monkeypatch):
    captured = {}

    def fake_post(base, path, token, body):
        captured.update(base=base, path=path, token=token, body=body)
        return 200, {"recorded": True}

    monkeypatch.setattr(wallet, "http_post", fake_post)
    g = PwmGate(token="pwm_x", base="http://host", enabled=True)
    ok = g.post_usage(contribution_id="ci-sol-1", agent_name="computational-imaging",
                      turn_id="job1")
    assert ok is True
    assert captured["path"] == "/api/v1/agent-pool/usage"
    assert captured["token"] == "pwm_x"
    assert captured["body"]["contribution_id"] == "ci-sol-1"
    assert captured["body"]["agent_name"] == "computational-imaging"
    assert captured["body"]["turn_id"] == "job1"


# ── cassi_dispatch posts usage on a confirmed paid run with a solution ─────
def test_cassi_dispatch_logs_usage(monkeypatch, tmp_path):
    from ai4science.harness import cassi_tools

    class _Prov:
        provider_id = "gpu"
        endpoint_path = str(tmp_path)
        wallet_address = "0x" + "a" * 40

    class _Job:
        job_id = "job-xyz"

    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda p: _Prov())
    monkeypatch.setattr(cassi_tools, "dispatch_job", lambda **k: _Job())
    monkeypatch.setattr(cassi_tools, "_contained", lambda ws, s: None)

    captured = {}

    class _FakeGate:
        def post_usage(self, **kw):
            captured.update(kw)
            return True

    monkeypatch.setattr(PwmGate, "from_env", classmethod(lambda cls: _FakeGate()))

    tool = {t.name: t for t in cassi_tools.cassi_tools()}["cassi_dispatch"]
    out = tool.func(str(tmp_path), benchmark="L3-x", solution_ref="ci-sol-1", confirm=True)

    assert "Dispatched job job-xyz" in out
    assert captured == {"contribution_id": "ci-sol-1",
                        "agent_name": "computational-imaging",
                        "turn_id": "job-xyz"}


def test_cassi_dispatch_no_solution_no_usage(monkeypatch, tmp_path):
    from ai4science.harness import cassi_tools

    class _Prov:
        provider_id = "gpu"
        endpoint_path = str(tmp_path)
        wallet_address = "0x" + "a" * 40

    class _Job:
        job_id = "job-2"

    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda p: _Prov())
    monkeypatch.setattr(cassi_tools, "dispatch_job", lambda **k: _Job())
    monkeypatch.setattr(cassi_tools, "_contained", lambda ws, s: None)

    called = {"n": 0}

    class _FakeGate:
        def post_usage(self, **kw):
            called["n"] += 1
            return True

    monkeypatch.setattr(PwmGate, "from_env", classmethod(lambda cls: _FakeGate()))

    tool = {t.name: t for t in cassi_tools.cassi_tools()}["cassi_dispatch"]
    # no solution_ref → user's own solver → no contribution usage to log
    tool.func(str(tmp_path), benchmark="L3-x", confirm=True)
    assert called["n"] == 0
