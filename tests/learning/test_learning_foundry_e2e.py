"""Appendix B sub-project 3f (Task 2): live-CP + real-podman drill. An
owner-minted+activated {domain:"learning", ceiling:"A1"} foundry agent authors a
grounded study guide + quiz and delivers only on a genuine CP-side quiz_check
grounding pass, UNDER ITS OWN identity; a no-domain agent through the SAME
run_foundry_agent is refused. Reuses the deterministic GroundedPlanner +
MATERIAL/DEMAND/_QUIZ/_GUIDE from tests/learning/test_agent_e2e.py (no LLM) and
the owner-signed foundry mint from tests/research/test_research_foundry_e2e.py."""
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

MATERIAL = {"m.txt": "Photosynthesis occurs in the chloroplast. "
                     "The mitochondria is the powerhouse of the cell.\n"}
DEMAND = {"topic": "cell biology", "material": MATERIAL,
          "min_questions": 2, "coverage_points": ["photosynthesis", "mitochondria"]}

_QUIZ = {"topic": "cell biology", "questions": [
    {"id": "q1", "type": "mcq", "prompt": "Where does photosynthesis occur?",
     "options": {"A": "nucleus", "B": "chloroplast"}, "answer": "B",
     "grounding": "Photosynthesis occurs in the chloroplast"},
    {"id": "q2", "type": "short", "prompt": "Powerhouse of the cell?",
     "answer": "mitochondria", "grounding": "mitochondria is the powerhouse of the cell"}]}
_GUIDE = "# Cell biology\n\nCovers photosynthesis in the chloroplast and the mitochondria.\n"


def _files():
    return {"study_guide.md": _GUIDE, "quiz.json": json.dumps(_QUIZ)}


class GroundedPlanner:
    def __init__(self, files):
        self._s = [PlanStep(summary="write", command=["true"], stage_files=files, request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True),
                   PlanStep(summary="give up", command=[], done=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass


def _serve_learning_owner():
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


def test_foundry_learning_agent_delivers_under_its_identity(tmp_path):
    server, uds, priv = _serve_learning_owner()
    try:
        client = ControlPlaneClient(uds)
        L = _mint(uds, priv, "tutor", "A1", domain="learning")
        out = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t1"),
                                agent_id=L, task_id="fl1", demand=DEMAND,
                                planner=GroundedPlanner(_files()), interaction_mode="I2")
        assert out["ok"] is True, out
        assert out["agent_id"] == L and out["ceiling"] == "A1"     # bound identity + derived ceiling
        assert out["result"]["status"] == "delivered", out         # CP quiz_check re-ran in a real container

        # same runner, a record with NO attested domain -> refused, no run.
        plain = _mint(uds, priv, "plain", "A1")                    # no domain
        ref = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t2"),
                                agent_id=plain, task_id="fl2", demand=DEMAND,
                                planner=GroundedPlanner(_files()), interaction_mode="I2")
        assert ref["ok"] is False and "domain" in ref["reason"].lower()
    finally:
        server.should_exit = True
