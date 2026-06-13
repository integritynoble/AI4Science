"""AI4Science agent-mining hooks — PwmGate.post_usage/post_feedback,
cassi_dispatch usage logging (E1), and the generic in-agent usage hook + /feedback."""
from ai4science.harness.pwm_gate import PwmGate, BASE_TOOLS
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


# ── in-agent generic usage hook (all agents) ──────────────────────────────
def test_on_tool_hook_fires_on_tool_use(tmp_path):
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.session import AgentSession
    from ai4science.harness.tools import default_registry
    from ai4science.harness.events import TextDelta, ToolCall, Usage, Done

    (tmp_path / "a.py").write_text("x = 1\n")
    script = [
        [ToolCall("c1", "read", {"path": "a.py"}), Usage(1, 1, 2), Done("tool_use")],
        [TextDelta("done"), Usage(1, 1, 2), Done("end")],
    ]
    used = []
    sess = AgentSession(adapter=StubAdapter(script), model="stub", backend="anthropic",
                        workspace=tmp_path, registry=default_registry(),
                        read_only=False, auto_yes=True, on_text=lambda t: None,
                        meter=lambda u: None, on_tool=lambda name: used.append(name))
    sess.run_turn("read a.py")
    assert "read" in used                       # the hook saw the tool invocation


def test_base_tools_excluded_from_mining():
    # base Claude-Code tools are infra; domain/capability tools are minable
    assert {"read", "write", "bash", "grep"} <= BASE_TOOLS
    assert "cassi_dispatch" not in BASE_TOOLS
    assert "compute_dispatch" not in BASE_TOOLS
    assert "pwm_solutions" not in BASE_TOOLS


# ── PwmGate.post_feedback ─────────────────────────────────────────────────
def test_post_feedback_no_login_uses_local_wallet(monkeypatch):
    """Zero-login (#2): with no account token, feedback still submits —
    identified by the auto-provisioned local wallet address, no Authorization."""
    cap = {}

    def fake_post(base, path, token, body):
        cap.update(path=path, body=body, token=token)
        return 200, {"status": "accepted", "reward": 0.5, "covers_turns": 12}

    monkeypatch.setattr(wallet, "http_post", fake_post)
    monkeypatch.setattr(wallet, "address", lambda: "0xLOCALWALLET")
    g = PwmGate(token=None, base="http://x", enabled=False)
    ok, status = g.post_feedback(agent_name="research", text="nice")
    assert ok is True
    assert cap["token"] is None                        # no account token sent
    assert cap["body"]["wallet"] == "0xLOCALWALLET"    # identified by local wallet
    assert cap["body"]["text"] == "nice"
    assert "earned 0.5 PWM" in status


def test_post_feedback_on_posts_to_active_agent(monkeypatch):
    cap = {}

    def fake_post(base, path, token, body):
        cap.update(path=path, body=body, token=token)
        return 200, {"status": "accepted"}

    monkeypatch.setattr(wallet, "http_post", fake_post)
    g = PwmGate(token="pwm_x", base="http://h", enabled=True)
    ok, status = g.post_feedback(agent_name="research", text="add streaming")
    assert ok is True and status == "accepted"
    assert cap["path"] == "/api/v1/agent-pool/research/feedback"
    assert cap["body"]["text"] == "add streaming"
    assert cap["token"] == "pwm_x"
