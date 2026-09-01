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
      ["openclaw", "acp", "--session", "agent:{openclaw_agent_id}:main"]

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
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

PROMPT_TIMEOUT = 600

#: How long the ACP `initialize` handshake may take.
#:
#: MEASURED, not chosen. The nightly live gate failed its first attempt on
#: every single scheduled run — 2026-08-28 (twice), 08-29, 08-30, 08-31 — always
#: with `TimeoutError: no response to initialize (id=1)`, and always passed on
#: the retry ~90s later. Seven for seven is not a flake, it is the normal cost
#: of first contact, and the retry was hiding it.
#:
#: Two back-to-back connections, same box, same agent:
#:
#:     cold   initialize  39.81s     session/new  0.60s
#:     warm   initialize   7.09s     session/new  0.30s
#:
#: The old value was 30s, so a cold handshake could not pass. `session/new` is
#: fast either way, which is what says the cost is in waking the agent runtime
#: rather than anywhere in the protocol.
#:
#: 180s is deliberately far above the 40s measured: this bounds a pathology, it
#: does not pace anything. A warm connect still returns in ~7s and pays none of
#: it, and the failure this replaces was a REAL transport that had simply not
#: finished waking. Raising it costs nothing on the happy path and stops the
#: gate from reporting a green PASS built on a retry.
CONNECT_TIMEOUT = 180
_CMD = ["opencode", "acp", "--pure"]  # kept for legacy; use openclaw_acp_runtime()

# The four-outcome verdict is shared with the sibling backend rather than
# re-implemented: one `classify` means a REFUSED reads ok=True on BOTH
# transports and a new stop reason cannot be judged two different ways.
from ai4science.harness.agents.sarsi.acp_backend import (
    _default_wire, agent_argv, classify, verdict_of)


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

    def connect(self, timeout: float = CONNECT_TIMEOUT) -> None:
        env = None
        if self._cmd and "openclaw" in str(self._cmd[0]):
            # openclaw is a Node.js script; ensure node is discoverable even
            # when the harness runs without the user's full NVM PATH.
            # RESOLVED, not assumed. This was hard-coded to
            # `/home/sarsi/.nvm/.../bin` — one specific account's node, in code
            # that runs on all of them. Every other account got a PATH pointing
            # into a home it cannot read (those are mode 750), so `openclaw`
            # never started and the only symptom was `initialize` timing out:
            # the transport looked broken when the interpreter was simply
            # somewhere else.
            import glob
            import os
            path = os.environ.get("PATH", "")
            if shutil.which("openclaw", path=path):
                node_bin = ""          # already reachable; touch nothing
            else:
                cands = sorted(glob.glob(
                    os.path.expanduser("~/.nvm/versions/node/*/bin")))
                node_bin = cands[-1] if cands else ""
            if node_bin and node_bin not in path:
                env = {**os.environ, "PATH": f"{node_bin}:{path}"}
        _refuse_if_spawn_disabled(self._cmd)
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

    def start(self, name: str, cwd: str, *, govern: bool = False,
              ceiling: str = "A0", writable: Optional[List[str]] = None,
              wire: Optional[Any] = None, **_: Any) -> Dict[str, Any]:
        """Open a session. When `govern=True`, the PreToolUse hook is written
        BEFORE the peer spawns and the session is REFUSED if it cannot be.

        `govern` defaults False here — the direct-`opencode` factories run
        ungoverned by design (opencode has no hook to govern against). But
        `session.assign` calls `start(..., govern=True, ...)` for the gateway
        path, and A used to swallow that through `**_` and spawn ungoverned
        anyway. Now the request is honoured or the session is refused, using the
        same writer (`_default_wire -> ensure_governance_hook`) the tmux path and
        the sibling backend use, so the two boundaries cannot drift.
        """
        if govern:
            try:
                (wire or _default_wire())(cwd, ceiling=ceiling, writable=writable)
            except Exception as e:
                # Not swallowed, and the peer is NOT spawned: an ungoverned
                # session is not the one that was asked for.
                return {"ok": False, "name": name, "cwd": cwd,
                        "reason": (f"could not govern the session: "
                                   f"{type(e).__name__}: {e} — not started, "
                                   f"because an ungoverned session is not the "
                                   f"one that was asked for")}
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


def acp_runtime_from_config(agent_id: str, *, config_path=None) -> AcpRuntime:
    """ACP runtime whose launch argv is RESOLVED FROM `openclaw.json`.

    The hardcoded factories (`acp_runtime`, `ai4sci_acp_runtime`,
    `openclaw_acp_runtime`) each bake in a fixed vector; none of them read the
    acpx entry's declared `args`. That is the bug `agent_argv` fixes — an entry
    of `{"command": ".../opencode", "args": ["acp"]}` must launch `opencode
    acp`, not bare `opencode` (which hangs forever on a non-TTY pipe). This
    factory reuses `agent_argv` (shared with `acp_backend`) so the direct
    transport honours the config the same way the backend does.
    """
    return _get_runtime(tuple(agent_argv(agent_id, config_path=config_path)))


SPAWN_DISABLED_ENV = "AI4SCIENCE_ACP_SPAWN_DISABLED"


def _refuse_if_spawn_disabled(argv) -> None:
    """Refuse to start a gateway bridge when the environment forbids it.

    A kill-switch for any environment that must never start one — a CI box, a
    sandbox, a test run. It is an ENVIRONMENT variable rather than a patch
    point on purpose, and the reason is a leak that could not be closed any
    other way.

    An `openclaw acp` bridge is a PAIR of processes and it detaches: the client
    is held in a module-level runtime cache, so when a test ends nothing stops
    it, and it keeps running with a cwd pointing at a pytest tmpdir that has
    since been deleted. Measured on agent-prod: 328 orphaned pairs holding 8 GB
    of RSS and 29.9 GB of swap, accumulated over three days.

    In-process monkeypatching closes that for tests that call this code
    directly, and five tests do not — they drive the real CLI in a SUBPROCESS,
    which has its own interpreter and never sees a patch. Their bridge is a
    GRANDCHILD of the test. An inherited environment variable is what reaches
    a grandchild; nothing in the parent's memory does.
    """
    import os
    if not os.environ.get(SPAWN_DISABLED_ENV):
        return
    raise AcpError(
        f"refusing to spawn an ACP bridge: {SPAWN_DISABLED_ENV} is set "
        f"({' '.join(map(str, argv))!r}).\n"
        "That pair detaches and outlives the process that started it. Inject a "
        "connect=/wire= fake, or unset the variable to allow a real bridge.")


def openclaw_agent_ids(home: Optional[str] = None) -> Optional[set]:
    """The agent ids openclaw is configured with, or None if unknowable.

    `None` and `set()` mean different things and the caller must not conflate
    them: None is "there is no readable config here", `set()` would be "the
    config says there are no agents". Only the second is evidence.
    """
    import os
    path = os.path.join(home or os.path.expanduser("~"),
                        ".openclaw", "openclaw.json")
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None
    listed = (cfg.get("agents") or {}).get("list") or []
    ids = {a.get("id") for a in listed if isinstance(a, dict) and a.get("id")}
    # `main` is the default agent and openclaw serves it whether or not the
    # list names it explicitly — this config's own list omits it.
    ids.add("main")
    return ids


def _require_openclaw_agent(openclaw_agent_id: str,
                            home: Optional[str] = None) -> None:
    """Fail the spawn when the gateway has no such agent.

    This is the root cause of the stall, stated plainly: the code asked for
    `sarsi-claude` and `openclaw agents list` held only `main` and `ops`. An
    unprefixed key hid that by creating a session under the default agent, so
    the misconfiguration presented as an hour of silence on the wrong model
    instead of an error naming the missing agent.

    Absence of evidence is not evidence of absence, so an unreadable or absent
    config raises NOTHING — the same rule the session-store lookup follows.
    Only a config that IS readable and does NOT list the agent is a finding.
    """
    known = openclaw_agent_ids(home)
    if known is None or openclaw_agent_id in known:
        return
    raise AcpError(
        f"openclaw has no agent {openclaw_agent_id!r} "
        f"(configured: {', '.join(sorted(known)) or 'none'}).\n"
        f"Without it the bridge would attach the session to the DEFAULT agent "
        f"— a different engine — and sit there. Register it with:\n"
        f"    openclaw agents add {openclaw_agent_id} \\\n"
        f"        --workspace ~/.openclaw/workspace-{openclaw_agent_id} \\\n"
        f"        --model anthropic/claude-opus-5 --non-interactive")


def openclaw_acp_runtime(openclaw_agent_id: str) -> AcpRuntime:
    """ACP runtime that drives an agent through the openclaw gateway.

    `openclaw acp --session agent:AGENT_ID:main` speaks the same JSON-RPC
    protocol over its stdin/stdout, and the gateway manages the agent's session
    — tool permissions and persistent history. (It does NOT open a tmux pane;
    this docstring said so for a while and openclaw's dist contains no tmux
    session management at all.)

    `openclaw_agent_id` is the agent's ID in openclaw.json (e.g.
    "sarsi-claude", "sarsi-open", "sarsi-ai4sci").

    Two things here were the gateway half of the `do → run → supervise` stall,
    and both were established by probing the live bridge rather than by reading
    the flags.

    **The key needs its `agent:` prefix.** `--session` takes
    `agent:<agent>:<session>` — the grammar of every key in the live store and
    every example in openclaw's own dist (`agent:main:main`, `agent:ops:work`).
    This emitted `f"{agent_id}:main:main"`.

    That did NOT "resolve to nothing", which is what this docstring claimed
    first and the store disproves. openclaw read the unprefixed string as a
    SESSION NAME belonging to the DEFAULT agent, and duly created it: the live
    store holds `agent:main:sarsi-claude:main:main`, `origin.label: "ACP"`,
    `totalTokens: 0`, `lastInteractionAt` equal to `sessionStartedAt`. So the
    bridge attached to agent `main` — a different engine entirely — under a
    junk session name, and no prompt ever reached a model. Nothing errored
    because, from openclaw's side, nothing was wrong.

    **The agent has to exist, and that is what must be checked.** The real
    cause was simply that no `sarsi-claude` agent was ever registered:
    `openclaw agents list` held only `main` and `ops`. `_require_openclaw_agent`
    therefore fails the spawn and names the agent and the command that creates
    it.

    **`--require-existing` is deliberately NOT passed**, and this is the
    correction to the first version of this fix. The flag is about the SESSION,
    not the agent: probed against a never-used key it makes `session/new`
    return `No session found: agent:sarsi-claude:brand-new-never-used`. Since a
    freshly registered agent has no sessions, passing it would turn every FIRST
    run on a new machine into a hard failure — trading an hour of silence for
    a permanent stop, and checking the wrong noun to do it.
    """
    import glob
    import os
    import shutil
    # PATH first, then THIS account's own nvm install. The fallback used to
    # name `/home/sarsi/.nvm/...` — one specific account's binary, in code that
    # runs on all of them. Every other account's homes are mode 750, so the
    # probe could not even stat it, and the only symptom was a timeout.
    binary = shutil.which("openclaw")
    if not binary:
        for _bin in sorted(glob.glob(
                os.path.expanduser("~/.nvm/versions/node/*/bin/openclaw"))):
            binary = _bin
        binary = binary or "openclaw"
    # The agent, not the session, is the thing that has to already exist.
    _require_openclaw_agent(openclaw_agent_id)
    cmd = (binary, "acp", "--session", f"agent:{openclaw_agent_id}:main")
    return _get_runtime(cmd)
