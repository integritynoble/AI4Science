"""Persistent ACP transport for openclaw-managed and ai4science sessions.

WHICH ACP MODULE TO USE (this file is the *transport*, sibling `acp_backend.py`
is the *backend*):

    Use `acp` (this module) when you want a PERSISTENT, RESUMABLE connection
    keyed by launch command — a cached `AcpRuntime` that holds one live process
    per session name and can `resume` a session after the gateway restarts. It
    drives `openclaw acp`, `ai4science acp` or bare `opencode` via the factory
    functions below.

    Use `acp_backend` (the sibling) when you START a governed, single-turn
    session and need a STRUCTURED verdict: the four outcomes
    (ANSWERED / REFUSED / ERRORED / SILENT), the PreToolUse governance hook
    written before the peer spawns, config-resolved agent argv, and the `spawn`
    report (running / finished / never_started / unknown).

The correctness fixes that were born in `acp_backend` — the four-outcome
`classify`, `agent_argv` (so a declared `["acp"]` vector is not dropped), and
the governance wire — are shared here rather than re-implemented: this module
imports them from `acp_backend` so the two boundaries cannot silently drift.

The tmux loop types at a screen and reads it back; this talks the Agent
Client Protocol directly over stdio JSON-RPC, so a prompt is a request with
an answer, not keystrokes followed by a guess. `AcpRuntime` exposes the same
surface `MachineRuntime` does — `start`, `send`, `stop`, `set_ceiling` —
plus `resume`, which re-opens a session after the gateway has died.

Two transport commands are supported:

  openclaw agent (sarsi-claude, sarsi-open, sarsi-ai4sci):
      ["openclaw", "acp", "--session", "{openclaw_agent_id}:main:main"]

  ai4science direct (fallback when the openclaw gateway is unavailable):
      ["/usr/local/bin/ai4science", "acp", "--pure", "--mode", MODE]

`openclaw acp` is the ACP bridge: it speaks ACP JSON-RPC over stdin/stdout
(NDJSON) and routes prompts through the OpenClaw Gateway (WebSocket) to the
target agent session. The protocol surface is identical to a direct
`opencode acp` server — `initialize`, `session/new`, `session/prompt`,
`session/update` — but the gateway handles session lifecycle, tool
permissions, and agent dispatch. The gateway also manages each agent's tmux
pane, giving human visibility alongside programmatic control.

`openclaw_acp_runtime(openclaw_agent_id)` returns a cached runtime that
drives the named openclaw agent via the gateway ACP bridge.
`ai4sci_acp_runtime(mode)` returns a cached runtime for a direct ai4science
ACP session (no gateway, no tmux pane).
"""
import json
import queue
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

PROMPT_TIMEOUT = 600
_CMD = ["opencode", "acp", "--pure"]  # kept for legacy; use openclaw_acp_runtime()

# The four-outcome verdict is shared with the sibling backend rather than
# re-implemented: one `classify` means a REFUSED reads ok=True on BOTH
# transports and a new stop reason cannot be judged two different ways.
from ai4science.harness.agents.sarsi.acp_backend import classify, verdict_of


def _verdict_for(reply: Dict[str, Any]) -> Dict[str, Any]:
    """Map an A-shaped `AcpClient.prompt` reply onto `classify`'s input.

    A speaks `stopReason` (camelCase) and reports transport failure as
    `{"ok": False, "reason": ...}`; `classify` speaks `stop_reason` and an
    `error` dict. This is the only adapter between the two shapes.
    """
    error = None
    if reply.get("ok") is False:
        error = {"message": reply.get("reason") or "the prompt did not succeed"}
    return classify({"stop_reason": reply.get("stopReason"),
                     "text": reply.get("text"),
                     "error": error})


class AcpError(Exception):
    """The protocol answered, and the answer was a refusal."""


class AcpClient:
    """One live `opencode acp --pure` process, one session, one inbox.

    The reader thread drains stdout into a queue. Responses to our requests
    are matched by id; agent-to-client requests (`session/request_permission`,
    the `fs/*` pair) are answered as they arrive, so a prompt never blocks on
    a permission it will grant itself.
    """

    def __init__(self, cwd: str, cmd: Optional[List[str]] = None):
        self.cwd = cwd
        self._cmd = cmd or _CMD
        self._inbox: "queue.Queue[str]" = queue.Queue()
        self._next_id = 0
        self._lock = threading.Lock()
        self._session_id: Optional[str] = None
        self._text: List[str] = []
        self._stop_reason: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None
        self._closed = False

    # -- lifecycle ---------------------------------------------------------

    def connect(self, timeout: float = 30.0) -> None:
        env = None
        if self._cmd and "openclaw" in str(self._cmd[0]):
            # openclaw is a Node.js script; ensure node is discoverable even
            # when the harness runs without the user's full NVM PATH.
            import os
            node_bin = "/home/sarsi/.nvm/versions/node/v24.19.0/bin"
            path = os.environ.get("PATH", "")
            if node_bin not in path:
                env = {**os.environ, "PATH": f"{node_bin}:{path}"}
        self._proc = subprocess.Popen(
            self._cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=self.cwd, text=True, bufsize=1,
            env=env)
        threading.Thread(target=self._read_loop, daemon=True).start()
        self._request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {},
        }, timeout)
        result = self._request("session/new", {
            "cwd": self.cwd,
            "mcpServers": [],
        }, timeout)
        self._session_id = result.get("sessionId")
        if not self._session_id:
            raise AcpError(f"session/new returned no sessionId: {result!r}")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        proc = self._proc
        if proc is None:
            return
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- prompting ---------------------------------------------------------

    def prompt(self, text: str, timeout: float = PROMPT_TIMEOUT) -> Dict[str, Any]:
        """Send one prompt and wait for its terminal answer.

        Returns `{"ok": True, "stopReason": ..., "text": ...}` on success,
        `{"ok": False, "reason": ...}` on protocol error or timeout. The
        caller treats `ok: False` as "the session did not take the brief",
        which is what the delivery path needs to decide whether to resume.
        """
        if not self.alive:
            return {"ok": False, "reason": "acp process is not running"}
        if not self._session_id:
            return {"ok": False, "reason": "no acp session was opened"}
        self._text = []
        self._stop_reason = None
        try:
            result = self._request("session/prompt", {
                "sessionId": self._session_id,
                "prompt": [{"type": "text", "text": text}],
            }, timeout)
        except AcpError as e:
            return {"ok": False, "reason": str(e)}
        except TimeoutError:
            return {"ok": False, "reason": f"prompt timed out after {int(timeout)}s"}
        return {"ok": True,
                "stopReason": self._stop_reason or result.get("stopReason"),
                "text": "".join(self._text)}

    # -- protocol plumbing -------------------------------------------------

    def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.strip()
            if line:
                self._inbox.put(line)

    def _send(self, obj: Dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        with self._lock:
            self._proc.stdin.write(json.dumps(obj) + "\n")
            self._proc.stdin.flush()

    def _request(self, method: str, params: Dict[str, Any],
                 timeout: float) -> Dict[str, Any]:
        with self._lock:
            self._next_id += 1
            rid = self._next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                    "params": params})
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self._inbox.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                raise TimeoutError(f"no response to {method} (id={rid})")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    err = msg["error"]
                    raise AcpError(f"{method} failed: {err.get('message', err)}")
                return msg.get("result") or {}
            self._handle_agent_message(msg)
        raise TimeoutError(f"timeout waiting for {method} (id={rid})")

    def _handle_agent_message(self, msg: Dict[str, Any]) -> None:
        method = msg.get("method")
        mid = msg.get("id")
        if method == "session/request_permission":
            params = msg.get("params") or {}
            options = params.get("options") or []
            pick = None
            for opt in options:
                if opt.get("kind") in ("allow_always", "allow_once"):
                    pick = opt.get("optionId")
                    break
            if pick is None and options:
                pick = options[0].get("optionId")
            if pick is not None:
                self._send({"jsonrpc": "2.0", "id": mid, "result": {
                    "outcome": {"outcome": "selected", "optionId": pick}}})
            return
        if method == "fs/read_text_file":
            self._send({"jsonrpc": "2.0", "id": mid, "result": {"content": ""}})
            return
        if method == "fs/write_text_file":
            self._send({"jsonrpc": "2.0", "id": mid, "result": {}})
            return
        if method == "session/update":
            update = (msg.get("params") or {}).get("update") or {}
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                self._text.append((update.get("content") or {}).get("text", ""))
            elif kind == "agent_thought_chunk":
                pass
            elif kind in ("tool_call", "tool_call_update"):
                pass
            return
        if mid is not None:
            # An agent request we do not recognise: acknowledge it rather
            # than leave the agent blocked on an unanswered call.
            self._send({"jsonrpc": "2.0", "id": mid, "result": {}})


class AcpRuntime:
    """The `MachineRuntime` surface, over ACP instead of tmux.

    `start` opens a session; `send` is a full prompt round-trip; `stop`
    closes the process; `set_ceiling` is a no-op because opencode has no
    hook to govern against (`govern=False` is forced for these sessions).
    `resume` re-opens a session for a name after a gateway restart, which
    is what lets a task continue at its first unverified phase.
    """

    acp = True

    def __init__(self, cmd: Optional[List[str]] = None) -> None:
        self._cmd = cmd or _CMD
        if cmd and "openclaw" in cmd[0]:
            self.engine = "openclaw"
        elif cmd and "ai4science" in cmd[0]:
            self.engine = "ai4science"
        else:
            self.engine = "opencode"
        self._clients: Dict[str, AcpClient] = {}

    def start(self, name: str, cwd: str, **_: Any) -> Dict[str, Any]:
        client = AcpClient(cwd, cmd=self._cmd)
        client.connect()
        self._clients[name] = client
        return {"ok": True, "name": name,
                "pid": client._proc.pid if client._proc else None,
                "cwd": cwd}

    def send(self, name: str, text: str, **_: Any) -> Dict[str, Any]:
        client = self._clients.get(name)
        if client is None or not client.alive:
            reply = {"ok": False, "reason": "no live acp session"}
            return {**reply, **_verdict_for(reply)}
        reply = client.prompt(text)
        # Enrich with the shared verdict while keeping A's original keys
        # (`ok`, `stopReason`, `text`, `reason`) untouched for existing callers.
        verdict = _verdict_for(reply)
        merged = dict(reply)
        merged.update({k: verdict[k] for k in
                       ("outcome", "refused", "attempted")})
        # `ok` is unified to the verdict's: a `refusal` is ok=True, a transport
        # failure is ok=False — which is what A already returned in both cases.
        merged["ok"] = verdict["ok"]
        return merged

    def stop(self, name: str, **_: Any) -> None:
        client = self._clients.pop(name, None)
        if client is not None:
            client.close()

    def set_ceiling(self, name: str, ceiling: str, **_: Any) -> Dict[str, Any]:
        # Nothing to raise: the ceiling is a tmux/governance concept and
        # opencode sessions run ungoverned by design.
        return {"ok": True}

    def resume(self, name: str, cwd: str, **_: Any) -> Dict[str, Any]:
        """Re-open a session for `name` after the gateway has restarted."""
        self.stop(name)
        return self.start(name, cwd)

    def close_all(self) -> None:
        for name in list(self._clients):
            self.stop(name)


_runtimes: Dict[tuple, AcpRuntime] = {}


def _get_runtime(cmd: tuple) -> AcpRuntime:
    """Return a cached AcpRuntime for this command, creating it on first use.

    Caching by command means `_rt()` in session.py always gets the same
    instance that `assign()` stored the AcpClient in — a fresh instance
    would have an empty `_clients` dict and lose the live session.
    """
    if cmd not in _runtimes:
        _runtimes[cmd] = AcpRuntime(cmd=list(cmd))
    return _runtimes[cmd]


def acp_runtime() -> AcpRuntime:
    """Legacy: ACP runtime for a direct opencode subprocess (no gateway)."""
    return _get_runtime(tuple(_CMD))


def ai4sci_acp_runtime(mode: str = "general-purpose") -> AcpRuntime:
    """ACP runtime that drives `ai4science acp --pure --mode MODE` directly.

    Used as a fallback when the openclaw gateway is unavailable. Prefer
    `openclaw_acp_runtime` for production sessions — it adds gateway-managed
    tmux visibility alongside programmatic control.
    """
    cmd = ("/usr/local/bin/ai4science", "acp", "--pure", "--mode", mode)
    return _get_runtime(cmd)


def openclaw_acp_runtime(openclaw_agent_id: str) -> AcpRuntime:
    """ACP runtime that drives an agent through the openclaw gateway.

    `openclaw acp --session AGENT_ID:main:main` speaks the same JSON-RPC
    protocol over its stdin/stdout, but the gateway manages the agent's
    session (in a tmux pane, with tool permissions, persistent history).
    The harness gets programmatic ACP control; the owner gets a visible pane.

    `openclaw_agent_id` is the agent's ID in openclaw.json (e.g.
    "sarsi-claude", "sarsi-open", "sarsi-ai4sci").
    """
    import os
    import shutil
    # Try current PATH first, then sarsi's NVM install as a fallback.
    _fallback = "/home/sarsi/.nvm/versions/node/v24.19.0/bin/openclaw"
    binary = shutil.which("openclaw") or (
        _fallback if os.path.isfile(_fallback) else "openclaw")
    cmd = (binary, "acp", "--session", f"{openclaw_agent_id}:main:main")
    return _get_runtime(cmd)
