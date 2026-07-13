"""Gated real-LLM RSI drill: a real LLMWorkPlanner drives the closed loop
(search -> validation) with N-repeat averaged, CP-computed scoring. Skips
unless podman AND ANTHROPIC_API_KEY AND PWM_WORK_LLM_TEST=1."""
import os, json, threading, time
import pytest
from pathlib import Path

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.sandbox import podman_available
from pwm_control_plane.work_scenes import generate_work_tasks

pytestmark = [
    pytest.mark.skipif(not podman_available(), reason="podman not installed"),
    pytest.mark.skipif(not (os.environ.get("ANTHROPIC_API_KEY")
                            and os.environ.get("PWM_WORK_LLM_TEST") == "1"),
                       reason="set ANTHROPIC_API_KEY and PWM_WORK_LLM_TEST=1 to run"),
]

def _serve_with_llm(tmp_path):
    import uvicorn
    from pwm_control_plane.config import Config
    from pwm_control_plane.audit import AuditLog
    from pwm_control_plane.governor import ResourceGovernor
    from pwm_control_plane.policy import PolicyEngine, generate_keypair, sign_bundle
    from pwm_control_plane.credentials import CredentialBroker, generate_fernet_key
    from pwm_control_plane.sandbox import SandboxExecutor
    from pwm_control_plane.service import build_app
    os.environ["PWM_CP_STATE_DIR"] = str(tmp_path)
    os.environ["PWM_CP_SOCKET"] = str(tmp_path / "cp.sock")
    cfg = Config.from_env(); cfg.ensure_dirs()
    priv, pub = generate_keypair()
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {"sandbox_exec": ["workspace/*"]}}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub); policy.load()
    broker = CredentialBroker(generate_fernet_key())
    broker.store_secret("llm", "ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path),
                    broker, SandboxExecutor())
    uds = tmp_path / "cp.sock"
    server = uvicorn.Server(uvicorn.Config(app, uds=str(uds), log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, str(uds)

def test_real_llm_drives_the_rsi_loop(tmp_path):
    from ai4science.harness.control_plane.client import ControlPlaneClient
    from ai4science.harness.runtime.task_store import TaskStore
    from ai4science.harness.agents.work.rsi_llm import run_work_rsi_search_llm
    server, uds = _serve_with_llm(tmp_path)
    try:
        generate_work_tasks(Path(tmp_path) / "eval", [0, 1], domain="work_search")
        generate_work_tasks(Path(tmp_path) / "eval", [0], domain="work_val")
        client = ControlPlaneClient(uds)
        res = run_work_rsi_search_llm(
            client=client, store_factory=lambda: TaskStore(tmp_path / f"t-{time.monotonic_ns()}"),
            search_task_ids=[0, 1], val_task_ids=[0], repeats=3)
        assert res["best_config"] is not None
        assert res["search_pass"] is not None and 0.0 <= res["search_pass"] <= 1.0
        assert res["val_pass"] is not None and 0.0 <= res["val_pass"] <= 1.0
        print(f"real-LLM RSI: best={res['best_config']} search={res['search_pass']} val={res['val_pass']}")
    finally:
        server.should_exit = True
