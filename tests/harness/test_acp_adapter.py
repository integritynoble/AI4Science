"""The ai4science ACP adapter, driven the way acpx drives it.

Promoted from the `ai4sci-agent-trio` task directory, where it passed p4 and p5
on the ai4science machine but existed only there — one unpushed copy on one
machine. These tests are what it did not have, and they are written against the
two things that actually break:

* the WIRE — so the adapter is spawned as a real subprocess and spoken to in
  JSON-RPC, rather than having its methods called;
* the TRANSCRIPT PARSER — the harness paints ANSI, marks replies with ❯ and ends
  turns with ✶, and a parser tested only on hand-written fixtures matches
  cleanly on those and finds nothing on a real run.

The engine is stubbed, not the protocol: `AI4SCI_ACP_PYTHON` points at a script
that emits a canned harness transcript, so every layer between the ACP frame and
the parsed answer is the real one.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai4science.harness.acp import server as acp

REPO = Path(__file__).resolve().parents[2]

#: What the harness really prints: ANSI colour, a banner naming the mode, the
#: pwm line carrying the resumable session id, the reply after ❯, and the ✶ turn
#: summary. Taken from the shape the adapter's regexes were written against.
TRANSCRIPT = (
    "\x1b[2m  ai4science 1.1.7\x1b[0m\n"
    "  agent  Unified-LLM  ·  Opus 5 (anthropic)\n"
    "  pwm    gate on — 12.5 PWM · session b38a7e88d479742c "
    "(resume: --resume b38a7e88d479742c)\n"
    "\x1b[36m❯\x1b[0m The ceiling is set by the collimation, not the geometry.\n"
    "  A second line of the same reply.\n"
    "✶ crunched 2s · 2.2k tokens\n"
    "❯ [harness] bye\n"
)


def _fake_engine(tmp_path, transcript=TRANSCRIPT, rc=0):
    """A stand-in for the interpreter the adapter invokes.

    The adapter runs `<python> -m ai4science.cli chat --mode ...`; this script
    ignores the arguments and prints a transcript, which is exactly the seam a
    test needs and the only thing it should replace.
    """
    p = tmp_path / "fake_engine.py"
    p.write_text(
        "import sys\n"
        "sys.stdin.read()\n"
        "sys.stdout.write(%r)\n"
        "sys.exit(%d)\n" % (transcript, rc))
    sh = tmp_path / "fake_engine.sh"
    sh.write_text("#!/bin/sh\nexec %s %s\n" % (sys.executable, p))
    sh.chmod(0o755)
    return str(sh)


class Adapter:
    def __init__(self, tmp_path, env_extra=None, transcript=TRANSCRIPT, rc=0):
        env = dict(os.environ)
        env.update({
            "AI4SCI_ACP_PYTHON": _fake_engine(tmp_path, transcript, rc),
            "AI4SCI_ACP_RECORDS": str(tmp_path / "records"),
            "PYTHONPATH": str(REPO) + os.pathsep + env.get("PYTHONPATH", ""),
        })
        env.update(env_extra or {})
        self.records = tmp_path / "records"
        self.p = subprocess.Popen(
            [sys.executable, "-m", "ai4science.harness.acp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            cwd=str(REPO), env=env)
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
            self.p.wait(timeout=30)
        except Exception:
            self.p.kill()


@pytest.fixture
def adapter(tmp_path):
    a = Adapter(tmp_path)
    yield a
    a.close()


def _session(a, cwd):
    a.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    msg, _ = a.request("session/new", {"cwd": str(cwd), "mcpServers": []})
    return msg["result"]["sessionId"]


# ----------------------------------------------------------------- the wire

def test_initialize_negotiates_the_version_the_sdk_speaks(adapter):
    msg, _ = adapter.request("initialize", {"protocolVersion": 1,
                                            "clientCapabilities": {}})
    r = msg["result"]
    assert r["protocolVersion"] == 1
    assert r["agentInfo"]["name"] == "ai4sci-agent-acp"
    assert r["authMethods"] == [], (
        "this adapter holds no credential of its own; advertising an auth "
        "method would invite the client to try to satisfy one")


def test_a_client_asking_for_a_newer_version_is_answered_with_ours(adapter):
    msg, _ = adapter.request("initialize", {"protocolVersion": 7,
                                            "clientCapabilities": {}})
    assert msg["result"]["protocolVersion"] == 1


def test_a_turn_is_answered_and_streamed_before_the_reply(adapter, tmp_path):
    sid = _session(adapter, tmp_path)
    msg, notes = adapter.request("session/prompt", {
        "sessionId": sid, "prompt": [{"type": "text", "text": "what sets it"}]})
    assert msg["result"]["stopReason"] == "end_turn"
    chunks = [n for n in notes if n.get("method") == "session/update"]
    assert chunks, "the answer arrived only in the reply — a client that renders "\
                   "streaming updates would show an empty turn"
    said = chunks[0]["params"]["update"]["content"]["text"]
    assert "collimation" in said
    assert "\x1b[" not in said, "ANSI escapes leaked into the ACP content block"
    assert "[harness] bye" not in said, "the /exit acknowledgement is not the reply"


def test_an_unknown_session_is_a_jsonrpc_error_not_a_death(adapter):
    adapter.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    msg, _ = adapter.request("session/prompt", {
        "sessionId": "ai4sci-nope", "prompt": [{"type": "text", "text": "hi"}]})
    assert msg["error"]["code"] == -32603
    assert adapter.p.poll() is None, "the adapter exited instead of reporting"


def test_an_unsupported_method_is_method_not_found(adapter):
    adapter.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    msg, _ = adapter.request("session/load", {"sessionId": "x", "cwd": "/tmp",
                                              "mcpServers": []})
    assert msg["error"]["code"] == -32601
    assert adapter.p.poll() is None


def test_a_turn_that_produced_nothing_is_a_refusal(tmp_path):
    """An executor that answers nothing must not look like one that answered.
    A silent empty reply is how a broken executor passes for a working one."""
    a = Adapter(tmp_path, transcript="\x1b[2m  ai4science\x1b[0m\nno LLM available\n")
    try:
        sid = _session(a, tmp_path)
        msg, notes = a.request("session/prompt", {
            "sessionId": sid, "prompt": [{"type": "text", "text": "hi"}]})
        assert msg["result"]["stopReason"] == "refusal"
        said = " ".join(n["params"]["update"]["content"]["text"]
                        for n in notes if n.get("method") == "session/update")
        assert "no reply" in said and "no LLM" in said
    finally:
        a.close()


def test_the_session_is_recorded_with_the_mode_it_actually_ran(adapter, tmp_path):
    sid = _session(adapter, tmp_path)
    adapter.request("session/prompt", {"sessionId": sid,
                                       "prompt": [{"type": "text", "text": "hi"}]})
    rec = (adapter.records / ("%s.log" % sid)).read_text()
    assert "mode_requested=%s" % acp.MODE in rec
    assert "mode_fallback=" in rec, (
        "the record must say whether the mode asked for is the mode that ran")
    assert "--- transcript ---" in rec and "collimation" in rec


# ------------------------------------------------------------ the parser

def test_the_parser_reads_a_painted_transcript():
    p = acp.parse_transcript(TRANSCRIPT)
    assert p["answer"].startswith("The ceiling is set by the collimation")
    assert "A second line of the same reply." in p["answer"]
    assert p["harness_session"] == "b38a7e88d479742c"
    assert p["mode"] == "Unified-LLM"
    assert p["failure"] is None


def test_a_mode_fallback_is_caught_rather_than_read_as_success():
    """The banner is the ONLY thing distinguishing a resolved mode from a
    silently substituted one — the `agent <label>` line looks identical either
    way. An adapter that misses it reports the wrong mode as fact."""
    p = acp.parse_transcript(
        "Unknown --mode 'ai4sci'; using 'unified-LLM'. Available: research\n"
        + TRANSCRIPT)
    assert p["mode_requested"] == "ai4sci"
    assert p["mode_fallback"] == "unified-LLM"


def test_the_farewell_is_never_mistaken_for_the_answer():
    p = acp.parse_transcript("❯ [harness] bye\n")
    assert p["answer"] == ""


# ------------------------------------------- the requirement, negatively

def test_claude_is_removed_from_the_environment_the_engine_inherits(tmp_path):
    """Not a fixture — the executor's standing guarantee. A PATH entry goes only
    if it really provides a `claude`, so unrelated tooling on the same directory
    is not collateral."""
    has = tmp_path / "withclaude"
    hasnt = tmp_path / "plain"
    has.mkdir()
    hasnt.mkdir()
    (has / "claude").write_text("#!/bin/sh\n")
    (has / "claude").chmod(0o755)
    (hasnt / "something-else").write_text("#!/bin/sh\n")

    env = acp.drop_claude_from_env({
        "PATH": os.pathsep.join([str(has), str(hasnt)]),
        "ANTHROPIC_API_KEY": "sk-should-not-survive",
        "CLAUDECODE": "1", "KEEP_ME": "yes"})
    parts = env["PATH"].split(os.pathsep)
    assert str(has) not in parts, "a directory providing claude survived"
    assert str(hasnt) in parts, "an unrelated directory was dropped as collateral"
    for gone in ("ANTHROPIC_API_KEY", "CLAUDECODE"):
        assert gone not in env
    assert env["KEEP_ME"] == "yes"


def test_the_adapter_names_no_claude_anywhere_in_its_code():
    """Docstrings stripped via ast: these files DISCUSS what they replace at
    length, and a prose mention of Claude is the opposite of a dependency."""
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
    # The scrubber must NAME what it removes, so those strings are expected in
    # exactly one function. Everything else must be clean.
    body = body.replace("'claude'", "").replace('"claude"', "")
    for forbidden in ("ClaudeAgent", "claude_agent", "claude-agent-acp",
                      "anthropic", "--agent"):
        assert forbidden not in body, (
            "%r appears in the adapter's code — the executor would need Claude"
            % forbidden)


def test_importing_the_adapter_pulls_in_no_claude_module():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, ai4science.harness.acp;"
         "print(','.join(k for k in sys.modules if 'claude' in k.lower()))"],
        capture_output=True, text=True, cwd=str(REPO), env=env)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "", "importing the adapter pulled in %s" % out.stdout.strip()


def test_the_engine_path_names_the_package_actually_running():
    """The skew `test_generator_runs_the_same_code.py` exists to refuse: a child
    started elsewhere imports whatever copy sits in its cwd. Here it must import
    the same ai4science this adapter did."""
    import ai4science
    assert acp.engine_path() == str(Path(ai4science.__file__).resolve().parent.parent)
