import json, threading, time
import uvicorn, pytest
from pathlib import Path
from ai4science.harness.control_plane.client import ControlPlaneClient

pwm_cp = pytest.importorskip("pwm_control_plane")  # skip if CP not installed in this env

def _serve(tmp_path):
    from pwm_control_plane.config import Config
    from pwm_control_plane.audit import AuditLog
    from pwm_control_plane.governor import ResourceGovernor
    from pwm_control_plane.policy import PolicyEngine, generate_keypair, sign_bundle
    from pwm_control_plane.service import build_app
    import os
    os.environ["PWM_CP_STATE_DIR"] = str(tmp_path)
    os.environ["PWM_CP_SOCKET"] = str(tmp_path / "cp.sock")
    cfg = Config.from_env(); cfg.ensure_dirs()
    priv, pub = generate_keypair()
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {"sandbox_exec": ["workspace/*"]}}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub); policy.load()
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path))
    uds = tmp_path / "cp.sock"
    server = uvicorn.Server(uvicorn.Config(app, uds=str(uds), log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started: break
        time.sleep(0.05)
    return server, str(uds)

def test_round_trip(tmp_path):
    server, uds = _serve(tmp_path)
    try:
        c = ControlPlaneClient(uds)
        assert c.healthz() is True
        run = c.open_run("g", "A1", {"actions": 3})
        d = c.authorize(run["run_id"],
                        {"action_type": "sandbox_exec", "target": "workspace/o.txt"})
        assert d["allowed"] is True
    finally:
        server.should_exit = True

def test_fail_closed_on_dead_socket(tmp_path):
    c = ControlPlaneClient(str(tmp_path / "nonexistent.sock"), timeout=0.5)
    d = c.authorize("run", {"action_type": "sandbox_exec", "target": "workspace/x"})
    assert d["allowed"] is False
    assert "unreachable" in d["reason"].lower()
    assert c.healthz() is False
