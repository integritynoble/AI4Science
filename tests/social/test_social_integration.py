"""Task 5: social-media agent end-to-end integration (podman-gated).

Proves the closed loop against a *mock* Mastodon instance through the live
control plane: a governed sandbox_execute reads the home timeline, a
deterministic draft is built, and posting only happens once the owner
approves -- with the Mastodon app token injected PROXY-SIDE (never visible
to the sandboxed agent or to the caller of ``run_social_task``).

Topology mirrors tests/imaging/test_rsi_round_integration.py /
tests/pwm-control-plane test_egress_integration.py: the mock Mastodon
HTTPServer runs on the HOST (127.0.0.1, ephemeral port); the sandbox
container is --network none, so its ONLY route to that mock is through the
control plane's per-run EgressProxy, bind-mounted in as a unix socket.

Note: real Mastodon instances are HTTPS, so ``EgressProxy._parse_host_scheme``
defaults a bare "host:port" allowlist entry to the "https" scheme. Our mock
is deliberately a plain ``http.server.HTTPServer`` (per the brief), so this
test monkeypatches that one default (scheme selection only) to "http" for
the duration of the test -- it does not touch policy/allowlist/injection
logic, the properties this test actually exercises.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import uvicorn

from pwm_control_plane.sandbox import podman_available

from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.agents.social.agent import run_social_task

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

SAMPLE_TIMELINE = [
    {"account": {"acct": "alice"}, "content": "hello from alice"},
    {"account": {"acct": "alice"}, "content": "alice again"},
    {"account": {"acct": "bob"}, "content": "bob checks in"},
]


def _make_mock_mastodon(posts: list):
    """Return an HTTPServer subclass handler bound to the given ``posts``
    list (append-only record of every accepted /api/v1/statuses POST)."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _reply_json(self, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/v1/timelines/home":
                self._reply_json(SAMPLE_TIMELINE)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/api/v1/statuses":
                length = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(length) if length else b""
                posts.append({"auth": self.headers.get("Authorization"),
                             "body": raw.decode("utf-8", "replace")})
                self._reply_json({"id": "123"})
            else:
                self.send_response(404)
                self.end_headers()

    return Handler


def _serve_social(mock_port: int, token: str):
    """Serve a fresh control-plane instance whose signed policy authorizes
    sandbox_exec (workspace/*) and network_egress to the mock Mastodon host,
    and whose credential broker holds the Mastodon app token under scope
    "mastodon". Mirrors tests/imaging/test_rsi_round_integration.py's
    ``_serve_with_owner``, but (a) adds the network_egress rule + broker
    secret this test needs and (b) uses a SHORT tempdir under /tmp rather
    than pytest's (often deep) tmp_path -- the per-run egress socket lives
    at ``<state_dir>/runs/<run_id>/egress.sock``, and AF_UNIX socket paths
    are capped at ~108 bytes.
    """
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
    cfg = Config.from_env()
    cfg.ensure_dirs()

    priv, pub = generate_keypair()
    host = f"127.0.0.1:{mock_port}"
    bundle = {"version": 1, "expires_at": time.time() + 3600,
              "rules": {"allow_action_targets": {
                  "sandbox_exec": ["workspace/*"],
                  "network_egress": [host],
              }}}
    (cfg.policy_dir / "rules.signed.json").write_text(json.dumps(sign_bundle(bundle, priv)))
    policy = PolicyEngine(cfg.policy_dir, pub)
    policy.load()

    broker = CredentialBroker(generate_fernet_key())
    broker.store_secret("mastodon", "MASTODON_TOKEN", token)

    executor = SandboxExecutor()
    app = build_app(cfg, policy, ResourceGovernor(), AuditLog(cfg.audit_path), broker, executor)

    uds = Path(state_dir) / "cp.sock"
    server = uvicorn.Server(uvicorn.Config(app, uds=str(uds), log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, str(uds)


def test_social_agent_e2e_read_draft_and_owner_gated_post(tmp_path, monkeypatch):
    # Real Mastodon instances are HTTPS; the mock here is deliberately plain
    # HTTP, so relax only the proxy's default scheme selection (not any
    # allowlist/injection/authorization logic) for a bare "host:port" entry.
    import pwm_control_plane.egress_proxy as egress_proxy_mod

    def _local_http_scheme(entry: str):
        if entry.startswith("http://"):
            return entry[len("http://"):], "http"
        if entry.startswith("https://"):
            return entry[len("https://"):], "https"
        return entry, "http"

    monkeypatch.setattr(egress_proxy_mod, "_parse_host_scheme", _local_http_scheme)

    posts: list = []
    Handler = _make_mock_mastodon(posts)
    mock = HTTPServer(("127.0.0.1", 0), Handler)
    mock_port = mock.server_address[1]
    threading.Thread(target=mock.serve_forever, daemon=True).start()

    server = None
    try:
        server, uds = _serve_social(mock_port, token="TESTTOKEN123")
        client = ControlPlaneClient(uds)
        host = f"127.0.0.1:{mock_port}"
        store = TaskStore(tmp_path / "t")

        # (a) approval withheld -> drafted; no external write; token hidden.
        out = run_social_task(client=client, store=store, task_id="s1",
                              mastodon_host=host, approve=None)
        assert out["status"] == "drafted", out
        assert posts == []                                    # no external write
        assert "TESTTOKEN123" not in json.dumps(out)          # token never in result

        # (b) approval granted -> posted; the mock only received the request
        # because the sandbox (--network none) went through the live egress
        # gate, and the Authorization header on it was injected proxy-side.
        out2 = run_social_task(client=client, store=store, task_id="s2",
                               mastodon_host=host, approve=lambda draft: True)
        assert out2["status"] == "posted", out2
        assert len(posts) == 1
        assert posts[0]["auth"] == "Bearer TESTTOKEN123"       # proxy injected the token
        assert "TESTTOKEN123" not in json.dumps(out2)          # still hidden from the agent
    finally:
        if server is not None:
            server.should_exit = True
        mock.shutdown()
        mock.server_close()
