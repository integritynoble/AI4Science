"""Task 10: end-to-end RSI round integration (podman-gated).

Proves the closed loop with real reconstructions and the live control plane:
seed held-out scenes -> run the candidate grid (scored by the live control
plane) -> a genuinely-better config wins on mean PSNR -> owner-signed
promote -> a subsequent run_imaging_task(governed=True) uses the promoted
config by default.
"""
import json
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from pwm_control_plane.sandbox import podman_available
from pwm_control_plane.eval_scenes import generate_held_out
from pwm_control_plane.owner_auth import sign_owner

from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.agents.imaging.rsi import run_rsi_round

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")


def _serve_with_owner(tmp_path):
    """Mirrors tests/test_control_plane_client.py::_serve, but also returns the
    owner private key -- the one whose public half PolicyEngine verifies both
    the policy bundle signature and owner_sig on /promote_version.
    """
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
    cfg = Config.from_env(); cfg.ensure_dirs()
    priv, pub = generate_keypair()
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {"sandbox_exec": ["workspace/*"]}}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub); policy.load()
    broker = CredentialBroker(generate_fernet_key())
    executor = SandboxExecutor()
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path), broker, executor)
    uds = tmp_path / "cp.sock"
    server = uvicorn.Server(uvicorn.Config(app, uds=str(uds), log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started: break
        time.sleep(0.05)
    return server, str(uds), priv


def test_rsi_round_to_promote_to_governed_run(tmp_path):
    server, uds, priv = _serve_with_owner(tmp_path)
    try:
        client = ControlPlaneClient(uds)

        # Seed the held-out scenes into the served instance's state dir
        # (_serve_with_owner set PWM_CP_STATE_DIR=tmp_path, so the held-out
        # store lives under tmp_path/"eval").
        generate_held_out(tmp_path / "eval", seeds=[301, 302])

        # Run the candidate grid, scored on both held-out scenes by the live CP.
        out = run_rsi_round(client=client, held_out_scene_ids=[0, 1],
                            seed_solver_ws=tmp_path / "seed")
        assert out["ranked"], out
        winner, winner_mean = out["ranked"][0]
        assert winner_mean is not None, out

        # Owner-signed promote of the winning config via the registry endpoint.
        ts = int(time.time())
        sig = sign_owner("promote", "agent", "imaging", winner, ts, priv)
        pr = client._client.post("/promote_version", json={
            "kind": "agent", "name": "imaging", "version": winner,
            "ts": ts, "owner_sig": sig, "eval_ref": out["eval_ref"],
        }).json()
        assert pr["ok"] is True, pr

        lkg = client.get_last_known_good("agent", "imaging")
        assert lkg["version"] == winner

        # A fresh governed task run now defaults to the promoted config.
        out2 = run_imaging_task(workspace=tmp_path / "seed2", client=client,
                                store=TaskStore(tmp_path / "t2"), task_id="rsi-e2e",
                                interaction_mode="I2", seed=42, governed=True)
        assert out2["status"] == "delivered", out2
    finally:
        server.should_exit = True
