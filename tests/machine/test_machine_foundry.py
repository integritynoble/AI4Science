"""Appendix B sub-project 3j (Task 1): machine as an ADVISORY foundry domain.
run_foundry_agent dispatches run_machine under an owner-attested {domain:"machine",
ceiling:"A0"} record WITHOUT opening a CP run or touching the sandbox; machine's
own closed-registry + owner-approve gate still fire through the dispatch; and a
foundry-dispatched op is audited to the CP log by default when the caller omits
audit= (gap-closer). NOTE: the foundry binding attests IDENTITY + gates DISPATCH
only; machine's host-side execution is governed by its own model, not the CP
ceiling (documented caveat)."""
import json, os, tempfile, threading, time
import httpx, uvicorn, pytest
from ai4science.harness.agents import foundry_runner as fr
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.agents.foundry_runner import run_foundry_agent

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.owner_auth import sign_owner_str
from pwm_control_plane.foundry import _hash

CAPS = {"os": "linux"}


class _NoExecClient:
    """Record source that FORBIDS CP execution (open_run/sandbox_execute raise if
    ever called) but DOES record audit_append calls (to verify the default sink)."""
    def __init__(self, rec):
        self._rec = rec
        self.audits = []
    def foundry_agent(self, aid): return self._rec
    def open_run(self, *a, **k): raise AssertionError("machine must not open a CP run")
    def sandbox_execute(self, *a, **k): raise AssertionError("machine must not touch the sandbox")
    def audit_append(self, kind, run_id, payload):
        self.audits.append({"kind": kind, "run_id": run_id, "payload": payload})
        return {"ok": True}


def _active(): return {"activation_state": "active", "ceiling": "A0", "domain": "machine"}


def test_machine_readonly_op_runs_without_cp_execution():
    c = _NoExecClient(_active())
    out = run_foundry_agent(client=c, store=object(), agent_id="D", task_id="t",
                            intent="detect my system info", caps=CAPS)
    assert out["ok"] is True and out["agent_id"] == "D" and out["ceiling"] == "A0"
    assert out["result"]["status"] == "done" and out["result"]["op"] == "detect"


def test_machine_no_match_refused():
    c = _NoExecClient(_active())
    out = run_foundry_agent(client=c, store=object(), agent_id="D", task_id="t",
                            intent="zzz nonsense xyz", caps=CAPS)
    assert out["ok"] is True and out["result"]["status"] == "refused"


def test_machine_consequential_without_approve_needs_approval():
    c = _NoExecClient(_active())
    out = run_foundry_agent(client=c, store=object(), agent_id="D", task_id="t",
                            intent="install claude code", caps=CAPS)   # no approve= supplied
    assert out["ok"] is True and out["result"]["status"] == "needs_approval"
    assert out["result"]["op"] == "install_claude_code"


def test_machine_omitted_audit_defaults_to_cp_audit_log():
    c = _NoExecClient(_active())
    out = run_foundry_agent(client=c, store=object(), agent_id="D", task_id="t",
                            intent="detect my system info", caps=CAPS)   # no audit= supplied
    assert out["result"]["status"] == "done"
    assert len(c.audits) == 1                                            # the op was audited to the CP log
    a = c.audits[0]
    assert a["kind"] == "machine_op" and a["payload"]["agent_id"] == "D"
    assert a["payload"]["op"] == "detect"                               # the machine event rode along


def test_machine_caller_audit_is_respected_over_default():
    c = _NoExecClient(_active())
    seen = []
    out = run_foundry_agent(client=c, store=object(), agent_id="D", task_id="t",
                            intent="detect my system info", caps=CAPS,
                            audit=lambda event: seen.append(event))
    assert out["result"]["status"] == "done"
    assert seen and seen[0]["op"] == "detect"                          # caller's audit received the event
    assert c.audits == []                                              # default did NOT override the caller


def test_machine_inactive_refused():
    c = _NoExecClient({"activation_state": "quarantined", "ceiling": "A0", "domain": "machine"})
    out = run_foundry_agent(client=c, store=object(), agent_id="D", task_id="t",
                            intent="detect", caps=CAPS)
    assert out["ok"] is False and "active" in out["reason"].lower()


def test_no_domain_refused():
    c = _NoExecClient({"activation_state": "active", "ceiling": "A0", "domain": ""})
    out = run_foundry_agent(client=c, store=object(), agent_id="D", task_id="t",
                            intent="detect", caps=CAPS)
    assert out["ok"] is False and "domain" in out["reason"].lower()


# ---- served-CP integration (no podman: machine opens no sandbox run) ----

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


def test_machine_foundry_served_cp():
    server, uds, priv = _serve_owner()
    try:
        client = ControlPlaneClient(uds)
        D = _mint(uds, priv, "mach", "A0", domain="machine")
        out = run_foundry_agent(client=client, store=object(), agent_id=D, task_id="d1",
                                intent="detect my system info", caps=CAPS)
        assert out["ok"] is True and out["agent_id"] == D and out["ceiling"] == "A0"
        assert out["result"]["status"] == "done" and out["result"]["op"] == "detect"

        plain = _mint(uds, priv, "plain", "A0")                     # no domain
        ref = run_foundry_agent(client=client, store=object(), agent_id=plain, task_id="d2",
                                intent="detect my system info", caps=CAPS)
        assert ref["ok"] is False and "domain" in ref["reason"].lower()
    finally:
        server.should_exit = True
