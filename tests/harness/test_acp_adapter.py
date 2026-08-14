"""The ai4science ACP adapter, driven the way acpx drives it.

Not mocked at the boundary that matters: the tests spawn
`python3 -m ai4science.harness.acp` as a real subprocess, speak JSON-RPC over
its stdio, and serve its LLM calls from a stub OpenAI-compatible HTTP server in
this process. So what is exercised is the actual wire on both sides — the
protocol frames acpx will send, and the `llm.openai_compat` path a local model
server answers.

The requirement being tested is p4's, and it is a negative one: *sarsi-claude
needs Claude; sarsi-ai4sci needs only ai4science.* A test that only checks the
adapter replies would pass just as well if it shelled out to Claude, so the
last test asserts what must be absent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


class _StubLLM(BaseHTTPRequestHandler):
    """The smallest thing that is an OpenAI-compatible chat endpoint."""

    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _StubLLM.seen.append(body)
        last = body["messages"][-1]["content"]
        out = json.dumps({
            "choices": [{"message": {"role": "assistant",
                                     "content": "stub saw: %s" % last}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5,
                      "total_tokens": 8}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):        # keep pytest output readable
        pass


@pytest.fixture
def stub_llm():
    _StubLLM.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _StubLLM)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d/v1" % srv.server_address[1]
    srv.shutdown()


class Adapter:
    """A spawned adapter, and the two calls a client makes to it."""

    def __init__(self, base, extra_env=None):
        env = dict(os.environ)
        env.update({"AI4SCIENCE_OPENAI_API_BASE": base,
                    "OPENAI_API_KEY": "stub-key-not-a-real-credential",
                    "AI4SCIENCE_OPENAI_MODEL": "stub-model",
                    "PYTHONPATH": str(REPO) + os.pathsep + env.get("PYTHONPATH", "")})
        env.update(extra_env or {})
        self.p = subprocess.Popen(
            [sys.executable, "-m", "ai4science.harness.acp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, cwd=str(REPO), env=env)
        self._id = 0

    def request(self, method, params):
        self._id += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id,
                                       "method": method, "params": params}) + "\n")
        self.p.stdin.flush()
        notes = []
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise AssertionError("adapter closed the stream; stderr:\n%s"
                                     % self.p.stderr.read())
            msg = json.loads(line)
            if msg.get("id") == self._id:
                return msg, notes
            notes.append(msg)

    def notify(self, method, params):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method,
                                       "params": params}) + "\n")
        self.p.stdin.flush()

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=20)
        except Exception:
            self.p.kill()


@pytest.fixture
def adapter(stub_llm):
    a = Adapter(stub_llm)
    yield a
    a.close()


def _session(adapter, tmp_path):
    adapter.request("initialize", {"protocolVersion": 1,
                                   "clientCapabilities": {}})
    msg, _ = adapter.request("session/new", {"cwd": str(tmp_path),
                                             "mcpServers": []})
    return msg["result"]["sessionId"]


# ----------------------------------------------------------------- handshake

def test_initialize_answers_the_protocol_version_the_sdk_speaks(adapter):
    msg, _ = adapter.request("initialize", {"protocolVersion": 1,
                                            "clientCapabilities": {}})
    r = msg["result"]
    assert r["protocolVersion"] == 1
    assert r["agentInfo"]["name"] == "ai4science"
    assert r["authMethods"] == [], (
        "this adapter holds no credential of its own; advertising an auth "
        "method would invite the client to try to satisfy one")


def test_a_session_is_bound_to_the_cwd_it_was_given(adapter, tmp_path):
    sid = _session(adapter, tmp_path)
    assert sid.startswith("ai4sci-")


# --------------------------------------------------------------------- turns

def test_a_prompt_is_answered_and_streamed_before_the_reply(adapter, tmp_path):
    sid = _session(adapter, tmp_path)
    msg, notes = adapter.request("session/prompt", {
        "sessionId": sid,
        "prompt": [{"type": "text", "text": "what is the ceiling"}]})
    assert msg["result"]["stopReason"] == "end_turn"
    chunks = [n for n in notes if n.get("method") == "session/update"]
    assert chunks, "the answer arrived only in the reply — a client that renders "\
                   "streaming updates would show an empty turn"
    up = chunks[0]["params"]["update"]
    assert up["sessionUpdate"] == "agent_message_chunk"
    assert "what is the ceiling" in up["content"]["text"]


def test_the_session_carries_its_history(adapter, tmp_path):
    sid = _session(adapter, tmp_path)
    adapter.request("session/prompt", {"sessionId": sid,
                                       "prompt": [{"type": "text", "text": "one"}]})
    adapter.request("session/prompt", {"sessionId": sid,
                                       "prompt": [{"type": "text", "text": "two"}]})
    last = _StubLLM.seen[-1]["messages"]
    roles = [m["role"] for m in last]
    assert roles == ["system", "user", "assistant", "user"], (
        "a session that forgets its own turn is a sequence of one-shots")


def test_an_unknown_session_is_refused_in_the_transcript_not_by_dying(adapter, tmp_path):
    adapter.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    msg, notes = adapter.request("session/prompt", {
        "sessionId": "ai4sci-nope", "prompt": [{"type": "text", "text": "hi"}]})
    assert msg["result"]["stopReason"] == "refusal"
    assert adapter.p.poll() is None, "the adapter exited instead of refusing"


def test_an_unsupported_method_is_a_jsonrpc_error_not_a_crash(adapter):
    adapter.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    msg, _ = adapter.request("session/load", {"sessionId": "x", "cwd": "/tmp",
                                              "mcpServers": []})
    assert msg["error"]["code"] == -32601
    assert adapter.p.poll() is None


def test_a_backend_that_is_not_there_refuses_with_a_usable_message(tmp_path):
    """The state the lane was actually parked in: no credential. It must say
    what to do, not fail the handshake."""
    a = Adapter("http://127.0.0.1:9/v1", extra_env={
        "AI4SCIENCE_OPENAI_API_BASE": "", "OPENAI_API_KEY": "",
        "AI4SCIENCE_ACP_BACKEND": ""})
    try:
        a.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        msg, _ = a.request("session/new", {"cwd": str(tmp_path), "mcpServers": []})
        sid = msg["result"]["sessionId"]
        msg, notes = a.request("session/prompt", {
            "sessionId": sid, "prompt": [{"type": "text", "text": "hi"}]})
        assert msg["result"]["stopReason"] == "refusal"
        said = " ".join(n["params"]["update"]["content"]["text"]
                        for n in notes if n.get("method") == "session/update")
        assert "localhost:11434" in said or "local server" in said, (
            "a refusal that does not say how to fix it costs a round trip with "
            "the owner: %s" % said)
    finally:
        a.close()


# ------------------------------------------------- the requirement, negatively

def test_the_adapter_never_reaches_for_claude(adapter, tmp_path):
    """p4 condition 1, as a test rather than as a config field.

    An adapter that satisfied every test above by shelling out to Claude Code
    would be exactly the thing this phase exists to replace. So: no Anthropic
    credential is read, no claude process is spawned, and the module graph the
    turn runs through does not contain the claude agent.
    """
    sid = _session(adapter, tmp_path)
    adapter.request("session/prompt", {"sessionId": sid,
                                       "prompt": [{"type": "text", "text": "hi"}]})
    # Every LLM call went to the stub, i.e. through ai4science's own llm layer.
    assert _StubLLM.seen, "the turn was served by something other than ai4science.llm"

    # Docstrings stripped via ast, not by guessing at line prefixes: these files
    # DISCUSS what they replace at length, and a prose mention of Claude is the
    # opposite of a dependency on it. What must be clean is the code.
    import ast

    def code_only(path):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                    and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body.pop(0)
        return ast.unparse(tree)

    src = REPO / "ai4science" / "harness" / "acp"
    body = "\n".join(code_only(p) for p in sorted(src.glob("*.py")))
    for forbidden in ("ClaudeAgent", "claude_agent", "ANTHROPIC_API_KEY",
                      "claude-agent-acp", "anthropic"):
        assert forbidden not in body, (
            "%r appears in the adapter's code — the executor would need Claude"
            % forbidden)


def test_the_adapter_imports_without_the_claude_agent_module(stub_llm):
    """The import graph, checked in a real interpreter: if driving ai4science
    dragged in the Claude agent, this is where it would show."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; import ai4science.harness.acp as m;"
         "bad=[k for k in sys.modules if 'claude' in k.lower()];"
         "print(','.join(bad))"],
        capture_output=True, text=True, cwd=str(REPO), env=env)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "", (
        "importing the adapter pulled in %s" % out.stdout.strip())
