"""Persistent ACP transport for opencode and ai4science sessions.

The tmux loop types at a screen and reads it back; this talks the Agent
Client Protocol directly over stdio JSON-RPC, so a prompt is a request with
an answer, not keystrokes followed by a guess. `AcpRuntime` exposes the same
surface `MachineRuntime` does — `start`, `send`, `stop`, `set_ceiling` —
plus `resume`, which re-opens a session after the gateway has died.

The command that backs each runtime is parameterised:
  - opencode:      ["opencode", "acp", "--pure"]
  - ai4science:    ["/usr/local/bin/ai4science", "acp", "--pure", "--mode", MODE]

`acp_runtime()` returns the singleton opencode runtime.
`ai4sci_acp_runtime(mode)` returns a cached runtime for that mode.
"""
import json
import queue
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

PROMPT_TIMEOUT = 600
_CMD = ["opencode", "acp", "--pure"]


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
        self._proc = subprocess.Popen(
            self._cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=self.cwd, text=True, bufsize=1)
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
        self.engine = "ai4science" if (cmd and "ai4science" in cmd[0]) else "opencode"
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
            return {"ok": False, "reason": "no live acp session"}
        return client.prompt(text)

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
    """The ACP runtime for opencode sessions."""
    return _get_runtime(tuple(_CMD))


def ai4sci_acp_runtime(mode: str = "general-purpose") -> AcpRuntime:
    """An ACP runtime that drives `ai4science acp --pure --mode MODE` sessions."""
    cmd = ("/usr/local/bin/ai4science", "acp", "--pure", "--mode", mode)
    return _get_runtime(cmd)
