"""Optional real-LLM drill: skipped unless ANTHROPIC_API_KEY is set AND
PWM_WORK_LLM_TEST=1. Serves a local control plane whose broker holds the
key under the 'llm' scope, then lets the real LLMWorkPlanner drive the task.
Asserts delivery or an honest blocker -- never a fabricated success."""
import json, os, threading, time
import pytest

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.sandbox import podman_available

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

def test_real_llm_work_task(tmp_path):
    from ai4science.harness.control_plane.client import ControlPlaneClient
    from ai4science.harness.runtime.task_store import TaskStore
    from ai4science.harness.agents.work.agent import run_work_task
    server, uds = _serve_with_llm(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        demand = {
            "objective": "fix add() in calc.py so that python3 tests_check.py exits 0",
            "input_files": {
                "calc.py": "def add(a, b):\n    return a - b\n",
                "tests_check.py": ("import sys\nfrom calc import add\n"
                                   "sys.exit(0 if add(1, 2) == 3 else 1)\n"),
            },
            "verify_commands": [["python3", "tests_check.py"]],
            "required_artifacts": ["calc.py"],
        }
        out = run_work_task(demand=demand, client=client,
                            store=TaskStore(tmp_path / "tasks"), task_id="live-work-1",
                            interaction_mode="I2", max_steps=12)
        assert out["status"] in ("delivered", "blocked")   # honest outcome either way
        print(f"real-LLM outcome: {out['status']}")        # informational
    finally:
        server.should_exit = True
