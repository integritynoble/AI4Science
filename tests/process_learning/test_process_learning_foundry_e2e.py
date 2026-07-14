"""Appendix B sub-project 3h (Task 2): live-CP + real-podman drill. An
owner-minted+activated {domain:"process_learning", ceiling:"A1"} foundry agent
authors a grounded explanation and delivers only on a genuine CP-side grounding
pass, UNDER ITS OWN identity; a no-domain agent through the SAME run_foundry_agent
is refused. Reuses the deterministic GroundedPlanner + TRACE/DEMAND/_GOOD from
tests/process_learning/test_agent_e2e.py (no LLM) and the owner-signed foundry
mint from tests/learning/test_learning_foundry_e2e.py."""
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

TRACE = {"journal.md": ("step 1: ran the GAP-TV solver. "
                        "step 2: the physics judge failed with a high residual. "
                        "step 3: increased iterations and the retry passed.\n")}
DEMAND = {"run_label": "cassi-run-42", "trace": TRACE, "coverage_points": ["retry", "judge"]}

_GOOD = (
    "# Postmortem: cassi-run-42\n\n"
    "The agent first ran the GAP-TV solver, then the physics judge failed [S1], so it "
    "increased iterations and the retry passed [S1]. The judge gating the outcome is "
    "the key control point in this run [S1].\n\n"
    "## References\n"
    'S1: trace/journal.md — "the physics judge failed"\n')


def _files():
    return {"explanation.md": _GOOD}


class GroundedPlanner:
    def __init__(self, files):
        self._s = [PlanStep(summary="write", command=["true"], stage_files=files, request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True),
                   PlanStep(summary="give up", command=[], done=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass


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


def test_foundry_process_learning_agent_delivers_under_its_identity(tmp_path):
    server, uds, priv = _serve_owner()
    try:
        client = ControlPlaneClient(uds)
        P = _mint(uds, priv, "postmortem", "A1", domain="process_learning")
        out = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t1"),
                                agent_id=P, task_id="fp1", demand=DEMAND,
                                planner=GroundedPlanner(_files()), interaction_mode="I2")
        assert out["ok"] is True, out
        assert out["agent_id"] == P and out["ceiling"] == "A1"     # bound identity + derived ceiling
        assert out["result"]["status"] == "delivered", out         # CP grounding checker re-ran in a real container

        # same runner, a record with NO attested domain -> refused, no run.
        plain = _mint(uds, priv, "plain", "A1")                    # no domain
        ref = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t2"),
                                agent_id=plain, task_id="fp2", demand=DEMAND,
                                planner=GroundedPlanner(_files()), interaction_mode="I2")
        assert ref["ok"] is False and "domain" in ref["reason"].lower()
    finally:
        server.should_exit = True
