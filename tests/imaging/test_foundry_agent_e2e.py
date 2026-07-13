"""Appendix B sub-project 3b (Task 4): live-CP + real-podman drill. An
owner-minted+activated imaging foundry agent runs a GENUINE GAP-TV
reconstruction to a real judge pass UNDER ITS OWN identity; an agent with no
attested domain is refused. Non-vacuous: the same runner handles both agents,
so the refusal proves the attestation is load-bearing (revert the domain
attestation or the binding and the pass assertion fails)."""
import json, threading, time
import httpx, uvicorn, pytest
from pathlib import Path
from pwm_control_plane.sandbox import podman_available
from pwm_control_plane.owner_auth import sign_owner_str
from pwm_control_plane.foundry import _hash
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.agents.foundry_runner import run_foundry_agent

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")


def _serve_owner(tmp_path):
    """Like tests.test_control_plane_client._serve but returns the owner
    private key (the bundle-signing key IS the owner key the service verifies)."""
    from pwm_control_plane.config import Config
    from pwm_control_plane.audit import AuditLog
    from pwm_control_plane.governor import ResourceGovernor
    from pwm_control_plane.policy import PolicyEngine, generate_keypair, sign_bundle
    from pwm_control_plane.credentials import CredentialBroker, generate_fernet_key
    from pwm_control_plane.sandbox import SandboxExecutor
    from pwm_control_plane.service import build_app
    import os
    os.environ["PWM_CP_STATE_DIR"] = str(tmp_path)
    os.environ["PWM_CP_SOCKET"] = str(tmp_path / "cp.sock")
    os.environ["PWM_CP_OWNER_MAX_CEILING"] = "A2"
    cfg = Config.from_env(); cfg.ensure_dirs()
    priv, pub = generate_keypair()
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {"sandbox_exec": ["workspace/*"]}}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub); policy.load()
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path),
                    CredentialBroker(generate_fernet_key()), SandboxExecutor())
    uds = tmp_path / "cp.sock"
    server = uvicorn.Server(uvicorn.Config(app, uds=str(uds), log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started: break
        time.sleep(0.05)
    return server, str(uds), priv


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
    rec = _post(uds, "/foundry/create", body)
    aid = rec["agent_id"]; ts2 = int(time.time())
    _post(uds, "/foundry/activate", {"agent_id": aid, "ts": ts2,
          "owner_sig": sign_owner_str(f"foundry_activate|{aid}|{ts2}", priv)})
    return aid


def test_foundry_imaging_agent_runs_end_to_end(tmp_path):
    server, uds, priv = _serve_owner(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        img = _mint(uds, priv, "imager", "A1", domain="imaging")
        out = run_foundry_agent(client=client, store=TaskStore(tmp_path / "tasks"),
                                agent_id=img, task_id="fa-e2e-1",
                                workspace=tmp_path / "seed", interaction_mode="I2",
                                seed=42, max_repairs=2, governed=False)
        assert out["ok"] is True, out
        assert out["agent_id"] == img and out["ceiling"] == "A1"   # ran under the record's identity+ceiling
        assert out["result"]["status"] == "delivered", out
        report = json.loads(Path(out["result"]["judge_report"]).read_text())
        assert report["final_decision"] == "pass", report          # real judge, real container

        # Same runner, a record with NO attested domain -> refused, no run.
        plain = _mint(uds, priv, "plain", "A1")                    # no domain
        ref = run_foundry_agent(client=client, store=TaskStore(tmp_path / "tasks2"),
                                agent_id=plain, task_id="fa-e2e-2",
                                workspace=tmp_path / "seed2")
        assert ref["ok"] is False and "domain" in ref["reason"].lower()
    finally:
        server.should_exit = True
