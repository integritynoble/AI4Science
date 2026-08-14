"""ai4science as an ACP agent — the executor that needs only ai4science.

The analogue of the bundled `@agentclientprotocol/claude-agent-acp`, for the
ai4science harness. OpenClaw's `runtime.type: "acp"` speaks JSON-RPC 2.0 over
this process's stdio; each `session/prompt` is served by running

    python -m ai4science.cli chat --mode ai4sci [--resume <id>]

in the session's cwd, and returning what the harness answered.

WHY A SUBPROCESS AND NOT AN IMPORT
    Because the MODE is the thing being measured. Importing the harness and
    calling an adapter directly would serve completions while skipping the mode,
    the banner, and the session ledger — which is exactly the defect that ruled
    out exposing ai4science as a model provider. Driving the CLI keeps the
    engine whole and leaves a session record with the mode named in it.

NO CLAUDE ANYWHERE
    This file names no Claude binary, SDK or provider, and never puts one on
    PATH — it removes it. `chat`'s `--agent` default is the string 'claude', so
    this adapter deliberately does NOT pass `--agent`: under the ai4sci mode the
    mode governs and that default is inert.

PROTOCOL
    ACP v1 (OpenClaw sends protocolVersion: 1). Newline-delimited JSON on stdio.
    stdout carries protocol traffic ONLY; every diagnostic goes to stderr.

KNOWN LIMITATION, stated rather than hidden
    The REPL reads one turn per line, so a multi-line prompt would be read as
    several turns. Newlines are collapsed to spaces and the collapse is logged to
    stderr and recorded in the session record. Prompts that need real newlines
    are not yet served faithfully.

PROVENANCE
    Written for the `ai4sci-agent-trio` queue task on the ai4science machine,
    where it passed p4 4/4 and p5 5/5 on 2026-08-14, and promoted here from
    `singularity-tasks/queue/ai4sci-agent-trio/adapters/ai4sci-agent-acp/`. It
    lived in a task directory on one machine, unpushed, beside an unpushed
    branch — the same single-copy exposure that has cost this project real work
    before. What changed on promotion is only what assumed that machine: the
    interpreter, the engine path and the records directory are derived or
    configured rather than written as absolute paths under one home directory.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

AGENT_NAME = "ai4sci-agent-acp"
AGENT_VERSION = "0.2.0"
PROTOCOL_VERSION = 1

#: The mode the engine is asked for. `ai4sci` is the current name; older installs
#: know it as `unified-LLM` and answer the fallback banner below, which is
#: detected rather than ignored — see `MODE_FALLBACK`.
MODE = os.environ.get("AI4SCI_ACP_MODE", "ai4sci")
TIMEOUT = int(os.environ.get("AI4SCI_ACP_TIMEOUT", "300"))
#: Read-only is the safe default for a package. An executor that must write —
#: which is the shape sarsi-claude has, and what p4's own marker requires —
#: sets this to 0 at the launcher, where the choice is visible.
READ_ONLY = os.environ.get("AI4SCI_ACP_READ_ONLY", "1") == "1"
# An ACP turn has no TTY. The harness gates Edit/Write/Bash behind an
# interactive "Type a number (1-3)" prompt, so WITHOUT auto-approve every
# side-effecting turn returns "[blocked] user decision" and the executor can
# never write the marker its own criterion demands. `--yes` governs `chat` and
# AI4SCIENCE_AUTO_YES governs the bare launch path; both are set.
AUTO_YES = os.environ.get("AI4SCI_ACP_AUTO_YES", "1") == "1"


def engine_python() -> str:
    """The interpreter that runs the engine.

    `sys.executable` by default, which is the one already running this adapter
    and therefore the one whose environment installed it. The original wrote an
    absolute path to one machine's venv because its launcher scrubbed PATH in
    shell, before an interpreter was chosen. Scrubbing inside Python instead
    (see `drop_claude_from_env`) makes the interpreter a known quantity, so the
    absolute path is no longer needed to survive it.
    """
    return os.environ.get("AI4SCI_ACP_PYTHON") or sys.executable


def engine_path() -> str:
    """Which `ai4science` package the engine imports.

    The gateway supplies the ACP session's cwd (the agent workspace), and
    `python -m` puts cwd first on `sys.path` — so without this the engine is
    whichever copy happens to sit in the caller's directory. This is the same
    skew `tests/research_agents/test_generator_runs_the_same_code.py` exists to
    refuse: two ends of one pipeline at different versions, where the quiet
    failure is a machine with a merely *stale* install answering with old code.
    Derived from this module's own import, so it names the copy actually running.
    """
    override = os.environ.get("AI4SCI_ACP_ENGINE_PATH")
    if override is not None:
        return override
    import ai4science
    return str(Path(ai4science.__file__).resolve().parent.parent)


def records_dir() -> Path:
    """Where session records land.

    Beside the data and cache, never beside the source: the original defaulted
    to a `records/` directory next to the adapter file, which is correct for a
    task directory and lands inside `site-packages` once this is installed.
    """
    return Path(os.environ.get("AI4SCI_ACP_RECORDS",
                               Path.home() / ".ai4science" / "acp-records"))


def drop_claude_from_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Make Claude Code unavailable to this process and everything it spawns.

    A gateway-spawned ACP agent inherits the gateway's PATH, which it cannot
    dictate from outside — so the executor removes it from its OWN environment
    before the engine starts. Every drop is surgical: a PATH entry goes only if
    it actually provides a `claude` executable, so unrelated tooling on the same
    directory survives or falls with it honestly.

    This is not a test fixture. It is the executor's standing guarantee that no
    session can reach Claude Code, on any machine, however the gateway's
    environment is configured — *sarsi-ai4sci needs only ai4science* enforced
    here rather than asserted in a report.
    """
    env = dict(os.environ if env is None else env)
    kept = []
    for d in (env.get("PATH") or "").split(os.pathsep):
        if not d:
            continue
        if os.access(os.path.join(d, "claude"), os.X_OK):
            continue
        kept.append(d)
    env["PATH"] = os.pathsep.join(kept)
    for var in ("CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE", "ANTHROPIC_API_KEY",
                "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(var, None)
    return env


# The harness paints its output; the literal bytes carry ANSI escapes, so every
# match below runs on stripped text. A naive match on the raw stream finds
# nothing on a real run while matching fine on a hand-written fixture.
ANSI = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")
# "  agent  Unified-LLM  ·  Opus 5 (anthropic)" — tui.py maps the mode id to a
# display label.
MODE_LINE = re.compile(r"^\s*agent\s+(\S+)", re.M)
# "Unknown --mode 'ai4sci'; using 'unified-LLM'. Available: ..." — commands/
# chat.py. This banner means the mode we ASKED for is not installed and the
# harness silently used its default. The `agent <label>` line looks identical
# either way, so a mode verdict that reads only MODE_LINE cannot tell a resolved
# mode from a fallback. Captured so the caller can refuse it.
MODE_FALLBACK = re.compile(r"Unknown --mode '([^']*)'; using '([^']*)'")
# "  pwm    gate on — ... · session b38a7e88d479742c (resume: --resume ...)"
SESSION_ID = re.compile(r"session\s+([0-9a-f]{8,})\s*\(resume:")
PROMPT_MARK = "❯"   # ❯ precedes each harness reply
TURN_END = "✶"      # ✶ crunched 2s · 2.2k tokens
FAILURE_MARKS = ("balance check failed", "invalid_token", "require_reauth",
                 "no LLM", "not installed", "insufficient")


def log(msg: str) -> None:
    print("[%s] %s" % (AGENT_NAME, msg), file=sys.stderr, flush=True)


def strip_ansi(s: str) -> str:
    return ANSI.sub("", s)


def parse_transcript(raw: str) -> Dict[str, Any]:
    """Pull the reply, the mode and the harness session id out of one run.

    The reply is delimited, not guessed: it runs from the first ❯ line that is
    not the harness's own farewell, up to the ✶ turn-summary line.
    """
    text = strip_ansi(raw)
    lines = text.splitlines()

    m = MODE_LINE.search(text)
    mode = m.group(1) if m else None

    m = SESSION_ID.search(text)
    sid = m.group(1) if m else None

    reply: List[str] = []
    collecting = False
    for line in lines:
        stripped = line.strip()
        if not collecting:
            if stripped.startswith(PROMPT_MARK):
                body = stripped[len(PROMPT_MARK):].strip()
                if body.startswith("[harness]"):
                    continue          # "❯ [harness] bye" — the /exit acknowledgement
                collecting = True
                if body:
                    reply.append(body)
            continue
        if stripped.startswith(TURN_END):
            break                     # end of this turn
        if stripped.startswith(PROMPT_MARK):
            body = stripped[len(PROMPT_MARK):].strip()
            if body.startswith("[harness]"):
                break
            reply.append(body)
            continue
        reply.append(line.rstrip())

    fb = MODE_FALLBACK.search(text)
    return {"answer": "\n".join(reply).strip(), "mode": mode,
            "harness_session": sid,
            "failure": next((f for f in FAILURE_MARKS if f in text), None),
            "transcript": text,
            "mode_requested": fb.group(1) if fb else None,
            "mode_fallback": fb.group(2) if fb else None}


class Session:
    def __init__(self, session_id: str, cwd: str) -> None:
        self.id = session_id
        self.cwd = cwd
        self.harness_session: Optional[str] = None
        self.turns = 0
        d = records_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.record = d / ("%s.log" % session_id)

    def append_record(self, header: str, body: str) -> None:
        with open(self.record, "a", encoding="utf-8") as fh:
            fh.write("\n===== %s =====\n%s\n" % (header, body))

    def run_turn(self, prompt: str) -> Dict[str, Any]:
        collapsed = " ".join(prompt.splitlines()).strip()
        if collapsed != prompt.strip():
            log("multi-line prompt collapsed to one line (see KNOWN LIMITATION)")

        cmd = [engine_python(), "-m", "ai4science.cli", "chat", "--mode", MODE]
        if READ_ONLY:
            cmd.append("--read-only")
        elif AUTO_YES:
            cmd.append("--yes")     # meaningless under --read-only; no tool to approve
        if self.harness_session:
            cmd += ["--resume", self.harness_session]

        env = drop_claude_from_env()
        if AUTO_YES and not READ_ONLY:
            env["AI4SCIENCE_AUTO_YES"] = "1"
        path = engine_path()
        if path:
            env["PYTHONPATH"] = (path + os.pathsep + env["PYTHONPATH"]
                                 if env.get("PYTHONPATH") else path)

        self.turns += 1
        started = time.time()
        log("turn %d in %s: %s" % (self.turns, self.cwd, " ".join(cmd)))
        try:
            proc = subprocess.run(
                cmd, cwd=self.cwd, input="%s\n/exit\n" % collapsed,
                capture_output=True, text=True, timeout=TIMEOUT, env=env)
            raw = (proc.stdout or "") + (proc.stderr or "")
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            raw, rc = "[adapter] timed out after %ds" % TIMEOUT, -1
        except OSError as e:
            raw, rc = "[adapter] could not start the engine: %s" % e, -1

        parsed = parse_transcript(raw)
        parsed["returncode"] = rc
        parsed["elapsed"] = round(time.time() - started, 2)
        if parsed["harness_session"] and not self.harness_session:
            self.harness_session = parsed["harness_session"]
            log("harness session bound: %s" % self.harness_session)

        if parsed["mode_fallback"]:
            log("MODE FALLBACK: asked %r, harness used %r"
                % (parsed["mode_requested"], parsed["mode_fallback"]))

        self.append_record(
            "turn %d  rc=%s  mode=%s  mode_requested=%s  mode_fallback=%s  "
            "harness_session=%s  elapsed=%ss\n--- prompt ---\n%s\n--- transcript ---"
            % (self.turns, rc, parsed["mode"], MODE,
               parsed["mode_fallback"] or "none", parsed["harness_session"],
               parsed["elapsed"], collapsed),
            parsed["transcript"])
        return parsed


class Server:
    def __init__(self, out=None) -> None:
        self.sessions: Dict[str, Session] = {}
        self.out = out if out is not None else sys.stdout

    # ---- wire ----------------------------------------------------------
    def send(self, obj: Dict[str, Any]) -> None:
        self.out.write(json.dumps(obj) + "\n")
        self.out.flush()

    def reply(self, req_id, result: Dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def error(self, req_id, code: int, message: str) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id,
                   "error": {"code": code, "message": message}})

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    # ---- methods -------------------------------------------------------
    def on_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        client = params.get("protocolVersion", PROTOCOL_VERSION)
        negotiated = min(int(client), PROTOCOL_VERSION)
        log("initialize: client asked v%s, serving v%s" % (client, negotiated))
        return {
            "protocolVersion": negotiated,
            "agentInfo": {"name": AGENT_NAME, "version": AGENT_VERSION},
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {"image": False, "audio": False,
                                       "embeddedContext": False},
            },
            # No auth methods: this adapter holds no credential of its own.
            "authMethods": [],
        }

    def on_session_new(self, params: Dict[str, Any]) -> Dict[str, Any]:
        cwd = params.get("cwd") or os.environ.get("AI4SCI_ACP_CWD") or os.getcwd()
        sid = "ai4sci-%s" % uuid.uuid4().hex[:16]
        self.sessions[sid] = Session(sid, str(cwd))
        log("session/new -> %s (cwd=%s)" % (sid, cwd))
        return {"sessionId": sid}

    def on_session_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sid = params.get("sessionId")
        session = self.sessions.get(sid)
        if session is None:
            raise KeyError("unknown sessionId %r" % sid)

        text = "\n".join(
            b.get("text", "") for b in params.get("prompt", [])
            if isinstance(b, dict) and b.get("type") == "text").strip()
        if not text:
            raise ValueError("prompt carried no text content block")

        result = session.run_turn(text)
        answer = result["answer"]

        if answer:
            self.notify("session/update", {
                "sessionId": sid,
                "update": {"sessionUpdate": "agent_message_chunk",
                           "content": {"type": "text", "text": answer}}})

        if result["failure"] or not answer:
            detail = result["failure"] or "harness returned no reply"
            log("turn did not produce a reply: %s" % detail)
            if not answer:
                self.notify("session/update", {
                    "sessionId": sid,
                    "update": {"sessionUpdate": "agent_message_chunk",
                               "content": {"type": "text",
                                           "text": "[%s] no reply: %s"
                                                   % (AGENT_NAME, detail)}}})
            return {"stopReason": "refusal"}
        return {"stopReason": "end_turn"}

    def on_session_cancel(self, params: Dict[str, Any]) -> None:
        log("session/cancel for %s (turns are atomic; nothing to interrupt)"
            % params.get("sessionId"))

    # ---- loop ----------------------------------------------------------
    def handle(self, msg: Dict[str, Any]) -> None:
        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        if method is None:
            return              # a response to something we sent; nothing to do

        try:
            if method == "initialize":
                self.reply(req_id, self.on_initialize(params))
            elif method == "authenticate":
                self.reply(req_id, {})
            elif method == "session/new":
                self.reply(req_id, self.on_session_new(params))
            elif method == "session/prompt":
                self.reply(req_id, self.on_session_prompt(params))
            elif method == "session/cancel":
                self.on_session_cancel(params)      # notification: no reply
            elif req_id is not None:
                self.error(req_id, -32601, "method not found: %s" % method)
            else:
                log("ignoring unknown notification %s" % method)
        except Exception as exc:                    # never die mid-session
            log("%s failed: %s: %s" % (method, type(exc).__name__, exc))
            if req_id is not None:
                self.error(req_id, -32603, "%s: %s" % (type(exc).__name__, exc))

    def serve(self, inp=None) -> int:
        log("ready — python=%s mode=%s records=%s"
            % (engine_python(), MODE, records_dir()))
        for line in (inp if inp is not None else sys.stdin):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError as exc:
                log("unparseable line dropped: %s" % exc)
                continue
            self.handle(msg)
        log("stdin closed — exiting")
        return 0


def serve(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        sys.stdout.write("%s %s (ACP protocol %d)\n"
                         % (AGENT_NAME, AGENT_VERSION, PROTOCOL_VERSION))
        return 0
    return Server().serve()
