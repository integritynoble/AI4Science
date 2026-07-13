"""Appendix B sub-project 3c (Task 2): live-CP + real-podman drill. An
owner-minted+activated {domain:"social", ceiling:"A2"} foundry agent reads a
mock Mastodon timeline (token hidden) and posts only on approval (token
proxy-injected, never in the result), UNDER ITS OWN identity; a no-domain
agent through the SAME run_foundry_agent is refused. Non-vacuous: reverting
the domain attestation or the agent binding fails it.

Mirrors tests/social/test_social_integration.py (mock host + egress gate +
credential injection) and tests/imaging/test_foundry_agent_e2e.py (owner-
signed foundry mint)."""
from __future__ import annotations
import json, os, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import httpx, uvicorn, pytest
from pwm_control_plane.sandbox import podman_available
from pwm_control_plane.owner_auth import sign_owner_str
from pwm_control_plane.foundry import _hash
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.agents.foundry_runner import run_foundry_agent

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

SAMPLE_TIMELINE = [
    {"account": {"acct": "alice"}, "content": "hello from alice"},
    {"account": {"acct": "bob"}, "content": "bob checks in"},
]


def _make_mock_mastodon(posts: list):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _reply_json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            if self.path == "/api/v1/timelines/home": self._reply_json(SAMPLE_TIMELINE)
            else: self.send_response(404); self.end_headers()
        def do_POST(self):
            if self.path == "/api/v1/statuses":
                length = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(length) if length else b""
                posts.append({"auth": self.headers.get("Authorization"),
                              "body": raw.decode("utf-8", "replace")})
                self._reply_json({"id": "123"})
            else: self.send_response(404); self.end_headers()
    return Handler


def _serve_social_owner(mock_port: int, token: str):
    """Serve a CP with the network_egress rule + broker token (like
    _serve_social) AND return the owner private key (like 3b's _serve_owner)
    so the test can owner-mint a foundry agent. Short /tmp state_dir keeps the
    per-run egress.sock path under the AF_UNIX ~108-byte cap."""
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
    host = f"127.0.0.1:{mock_port}"
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {
                  "sandbox_exec": ["workspace/*"], "network_egress": [host]}}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub); policy.load()
    broker = CredentialBroker(generate_fernet_key())
    broker.store_secret("mastodon", "MASTODON_TOKEN", token)
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path), broker, SandboxExecutor())
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


def test_foundry_social_agent_reads_and_owner_gated_posts(tmp_path, monkeypatch):
    import pwm_control_plane.egress_proxy as egress_proxy_mod
    def _local_http_scheme(entry):
        if entry.startswith("http://"): return entry[len("http://"):], "http"
        if entry.startswith("https://"): return entry[len("https://"):], "https"
        return entry, "http"
    monkeypatch.setattr(egress_proxy_mod, "_parse_host_scheme", _local_http_scheme)

    posts: list = []
    mock = HTTPServer(("127.0.0.1", 0), _make_mock_mastodon(posts))
    mock_port = mock.server_address[1]
    threading.Thread(target=mock.serve_forever, daemon=True).start()

    server = None
    try:
        server, uds, priv = _serve_social_owner(mock_port, token="TESTTOKEN123")
        client = ControlPlaneClient(uds)
        host = f"127.0.0.1:{mock_port}"
        S = _mint(uds, priv, "poster", "A2", domain="social")

        # (a) approval withheld -> drafted, no external write, token hidden, ran under S's identity.
        out = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t1"),
                                agent_id=S, task_id="fs1", mastodon_host=host, approve=None)
        assert out["ok"] is True, out
        assert out["agent_id"] == S and out["ceiling"] == "A2"      # bound identity + derived ceiling
        assert out["result"]["status"] == "drafted", out
        assert posts == []                                          # no external write
        assert "TESTTOKEN123" not in json.dumps(out)

        # (b) approval granted -> posted; token proxy-injected on the POST, hidden from the result.
        out2 = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t2"),
                                 agent_id=S, task_id="fs2", mastodon_host=host, approve=lambda d: True)
        assert out2["ok"] is True and out2["result"]["status"] == "posted", out2
        assert len(posts) == 1
        assert posts[0]["auth"] == "Bearer TESTTOKEN123"            # proxy injected the token
        assert "TESTTOKEN123" not in json.dumps(out2)               # still hidden from the agent

        # (c) same runner, a record with NO attested domain -> refused, no run.
        plain = _mint(uds, priv, "plain", "A2")                     # no domain
        ref = run_foundry_agent(client=client, store=TaskStore(tmp_path / "t3"),
                                agent_id=plain, task_id="fs3", mastodon_host=host, approve=None)
        assert ref["ok"] is False and "domain" in ref["reason"].lower()
    finally:
        if server is not None:
            server.should_exit = True
        mock.shutdown(); mock.server_close()
