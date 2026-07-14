"""Appendix B sub-project 3i (Task 1): pocket as an ADVISORY foundry domain.
run_foundry_agent dispatches run_pocket under an owner-attested {domain:"pocket",
ceiling:"A0"} record WITHOUT opening a CP run or touching the sandbox; pocket's
own permission gate + risk-ceiling handoff still fire through the dispatch.
Unknown/inactive/no-domain -> refused, nothing dispatched. NOTE: the foundry
binding attests IDENTITY + gates DISPATCH only; pocket's host-side execution is
governed by its own model, not the CP ceiling (documented caveat)."""
import json, os, tempfile, threading, time
import httpx, uvicorn, pytest
from ai4science.harness.agents import foundry_runner as fr
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.agents.foundry_runner import run_foundry_agent

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.owner_auth import sign_owner_str
from pwm_control_plane.foundry import _hash


class _NoExecClient:
    """A record source that FORBIDS CP execution: if the pocket dispatch ever
    opens a run or touches the sandbox, these raise -> the test fails."""
    def __init__(self, rec): self._rec = rec
    def foundry_agent(self, aid): return self._rec
    def open_run(self, *a, **k): raise AssertionError("pocket must not open a CP run")
    def sandbox_execute(self, *a, **k): raise AssertionError("pocket must not touch the sandbox")


def test_pocket_granted_intent_runs_without_cp_execution():
    c = _NoExecClient({"activation_state": "active", "ceiling": "A0", "domain": "pocket"})
    out = run_foundry_agent(client=c, store=object(), agent_id="K", task_id="t",
                            intent="jot this note: hello world", granted=("notes",))
    assert out["ok"] is True and out["agent_id"] == "K" and out["ceiling"] == "A0"
    assert out["result"]["status"] == "done"          # note_write executed host-side
    assert out["result"]["tool"] == "note_write"


def test_pocket_ungranted_tool_refused():
    c = _NoExecClient({"activation_state": "active", "ceiling": "A0", "domain": "pocket"})
    out = run_foundry_agent(client=c, store=object(), agent_id="K", task_id="t",
                            intent="jot this note: hello world", granted=())   # 'notes' NOT granted
    assert out["ok"] is True and out["result"]["status"] == "refused"   # pocket permission gate fired


def test_pocket_consequential_intent_handoff():
    c = _NoExecClient({"activation_state": "active", "ceiling": "A0", "domain": "pocket"})
    out = run_foundry_agent(client=c, store=object(), agent_id="K", task_id="t",
                            intent="buy a coffee", granted=("notes",))
    assert out["ok"] is True and out["result"]["status"] == "handoff"   # risk ceiling fired first
    assert out["result"]["kind"] == "spend"


def test_pocket_inactive_refused():
    c = _NoExecClient({"activation_state": "quarantined", "ceiling": "A0", "domain": "pocket"})
    out = run_foundry_agent(client=c, store=object(), agent_id="K", task_id="t",
                            intent="jot this note: hi", granted=("notes",))
    assert out["ok"] is False and "active" in out["reason"].lower()


def test_no_domain_refused():
    c = _NoExecClient({"activation_state": "active", "ceiling": "A0", "domain": ""})
    out = run_foundry_agent(client=c, store=object(), agent_id="K", task_id="t",
                            intent="jot this note: hi", granted=("notes",))
    assert out["ok"] is False and "domain" in out["reason"].lower()


# ---- served-CP integration (no podman: pocket opens no sandbox run) ----

def _serve_owner():
    from pwm_control_plane.config import Config
    from pwm_control_plane.audit import AuditLog
    from pwm_control_plane.governor import ResourceGovernor
    from pwm_control_plane.policy import PolicyEngine, generate_keypair, sign_bundle
    from pwm_control_plane.credentials import CredentialBroker, generate_fernet_key
    from pwm_control_plane.sandbox import SandboxExecutor
    from pwm_control_plane.service import build_app
    state_dir = tempfile.mkdtemp(dir="/tmp")
    os.environ["PWM_CP_STATE_DIR"] = state_dir
    os.environ["PWM_CP_SOCKET"] = str(os.path.join(state_dir, "cp.sock"))
    os.environ["PWM_CP_OWNER_MAX_CEILING"] = "A2"
    cfg = Config.from_env(); cfg.ensure_dirs()
    priv, pub = generate_keypair()
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {"sandbox_exec": ["workspace/*"]}}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub); policy.load()
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path),
                    CredentialBroker(generate_fernet_key()), SandboxExecutor())
    uds = os.path.join(state_dir, "cp.sock")
    server = uvicorn.Server(uvicorn.Config(app, uds=uds, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started: break
        time.sleep(0.05)
    return server, uds, priv


def _post(uds, path, body):
    with httpx.Client(transport=httpx.HTTPTransport(uds=uds), base_url="http://cp") as c:
        return c.post(path, json=body, timeout=15).json()


def _mint(uds, priv, name, ceiling, *, domain=""):
    ts = int(time.time())
    payload = f"foundry_create|clean_template|{name}|{ceiling}||{_hash({})}|{ts}"
    if domain:
        payload += f"|{domain}"
    body = {"creation_type": "clean_template", "name": name, "ceiling": ceiling,
            "parents": [], "goal": {}, "ts": ts, "owner_sig": sign_owner_str(payload, priv)}
    if domain:
        body["domain"] = domain
    aid = _post(uds, "/foundry/create", body)["agent_id"]
    ts2 = int(time.time())
    _post(uds, "/foundry/activate", {"agent_id": aid, "ts": ts2,
          "owner_sig": sign_owner_str(f"foundry_activate|{aid}|{ts2}", priv)})
    return aid


def test_pocket_foundry_served_cp():
    server, uds, priv = _serve_owner()
    try:
        client = ControlPlaneClient(uds)
        K = _mint(uds, priv, "pkt", "A0", domain="pocket")
        out = run_foundry_agent(client=client, store=object(), agent_id=K, task_id="k1",
                                intent="jot this note: hello", granted=("notes",))
        assert out["ok"] is True and out["agent_id"] == K and out["ceiling"] == "A0"
        assert out["result"]["status"] == "done" and out["result"]["tool"] == "note_write"

        plain = _mint(uds, priv, "plain", "A0")                     # no domain
        ref = run_foundry_agent(client=client, store=object(), agent_id=plain, task_id="k2",
                                intent="jot this note: hello", granted=("notes",))
        assert ref["ok"] is False and "domain" in ref["reason"].lower()
    finally:
        server.should_exit = True
