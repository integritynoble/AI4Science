"""Appendix B sub-project 3d (Task 2): live-CP + real-podman drill. An
owner-minted+activated {domain:"work", ceiling:"A1"} foundry agent authors a
fix and delivers only on a genuine CP-side command-judge pass, UNDER ITS OWN
identity; a no-domain agent through the SAME run_foundry_agent is refused.
Reuses the deterministic ScriptedPlanner + DEMAND from tests/work/test_agent_e2e.py
(no LLM) and the owner-signed foundry mint from tests/imaging/test_foundry_agent_e2e.py."""
from __future__ import annotations
import json, os, tempfile, threading, time
from pathlib import Path
import httpx, uvicorn, pytest
from pwm_control_plane.sandbox import podman_available
from pwm_control_plane.owner_auth import sign_owner_str
from pwm_control_plane.foundry import _hash
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.foundry_runner import run_foundry_agent

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

DEMAND = {
    "objective": "fix add() in calc.py so tests_check.py passes",
    "input_files": {
        "calc.py": "def add(a, b):\n    return a - b\n",
        "tests_check.py": ("import sys\nfrom calc import add\n"
                           "sys.exit(0 if add(1, 2) == 3 else 1)\n"),
    },
    "verify_commands": [["python3", "tests_check.py"]],
    "required_artifacts": ["calc.py"],
}


class ScriptedPlanner:
    """Deterministic stand-in for the LLM: fix the file, then request verify."""
    def __init__(self):
        self._steps = [
            PlanStep(summary="fix add()", command=["python3", "-c", "print('patched')"],
                     stage_files={"calc.py": "def add(a, b):\n    return a + b\n"},
                     request_verify=False),
            PlanStep(summary="verify success criteria", command=[], request_verify=True),
        ]
    def next_step(self, state):
        return self._steps.pop(0)
    def replan(self, state, verdict):
        pass


def _serve_work_owner():
    """Live CP with a real SandboxExecutor + a signed policy authorizing
    sandbox_exec on workspace/*, returning the owner private key so the test
    can owner-mint. Short /tmp state_dir keeps socket paths short."""
    from pwm_control_plane.config import Config
    from pwm_control_plane.audit import AuditLog
    from pwm_control_plane.governor import ResourceGovernor
    from pwm_control_plane.policy import PolicyEngine, generate_keypair, sign_bundle
    from pwm_control_plane.credentials import CredentialBroker, generate_fernet_key
    from pwm_control_plane.sandbox import SandboxExecutor
    from pwm_control_plane.service import build_app
    state_dir = tempfile.mkdtemp(dir="/tmp")
    os.environ["PWM_CP_STATE_DIR"] = state_dir
    os.environ["PWM_CP_SOCKET"] = str(Path(state_dir) / "cp.sock")
    os.environ["PWM_CP_OWNER_MAX_CEILING"] = "A2"
    cfg = Config.from_env(); cfg.ensure_dirs()
    priv, pub = generate_keypair()
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {"sandbox_exec": ["workspace/*"]}}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub); policy.load()
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path),
                    CredentialBroker(generate_fernet_key()), SandboxExecutor())
    uds = Path(state_dir) / "cp.sock"
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
    aid = _post(uds, "/foundry/create", body)["agent_id"]
    ts2 = int(time.time())
    _post(uds, "/foundry/activate", {"agent_id": aid, "ts": ts2,
          "owner_sig": sign_owner_str(f"foundry_activate|{aid}|{ts2}", priv)})
    return aid


def test_foundry_work_agent_delivers_under_its_identity(tmp_path):
    server, uds, priv = _serve_work_owner()
    try:
        client = ControlPlaneClient(uds)
        W = _mint(uds, priv, "worker", "A1", domain="work")
        out = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t1"),
                                agent_id=W, task_id="fw1", demand=DEMAND,
                                planner=ScriptedPlanner(), interaction_mode="I2")
        assert out["ok"] is True, out
        assert out["agent_id"] == W and out["ceiling"] == "A1"     # bound identity + derived ceiling
        assert out["result"]["status"] == "delivered", out         # CP judge re-ran tests in a real container

        # same runner, a record with NO attested domain -> refused, no run.
        plain = _mint(uds, priv, "plain", "A1")                    # no domain
        ref = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t2"),
                                agent_id=plain, task_id="fw2", demand=DEMAND,
                                planner=ScriptedPlanner(), interaction_mode="I2")
        assert ref["ok"] is False and "domain" in ref["reason"].lower()
    finally:
        server.should_exit = True
