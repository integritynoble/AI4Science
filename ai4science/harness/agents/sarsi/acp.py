"""Driving a session through **OpenClaw ACP** instead of through a screen.

WHAT THIS REPLACES, and why it is worth replacing.

`session.MachineRuntime` starts a tmux session and the supervision loop reads
the SESSION SCREEN to decide what happened. That has a recorded defect on this
machine: a screen-scoring verifier cannot distinguish a CORRECT REFUSAL from a
FAILURE, nor an IDLE session from a dead one. Both read FAIL. A backend that
declined a dangerous instruction and said why is scored the same as one that
crashed -- so the loop punishes the behaviour it exists to encourage.

ACP does not fix the scorer. It removes the need for one: the turn ends with a
STRUCTURED stop reason on the wire, and `refusal` is one of them. The verdict is
read, not inferred from pixels.

FOUR OUTCOMES, DELIBERATELY NOT THREE
    `ANSWERED`  the turn ended on its own terms.
    `REFUSED`   the agent declined. **ok is True.** This is a correct outcome
                and the reason travels with it.
    `ERRORED`   it attempted and something broke -- transport, spawn, a turn
                that ran out of budget, or a stop reason this code does not
                recognise. Unrecognised is reported, never guessed at.
    `SILENT`    nothing concluded. Not a refusal, not an error: the absence of
                a turn. Reporting it as either of the others is the lie the
                screen-scorer told.

ACCEPTANCE IS NOT A VERDICT
    A known consequence of the ACP spawn: the caller's turn returns at
    `accepted` while the executor runs on, so a naive caller reads "it started"
    as "it worked". `start` therefore returns `outcome: ACCEPTED` and
    `verdict_of` returns **None** for it. A verdict exists only after the YIELD
    -- `send`, which blocks for the turn's stop reason. There is no path from
    a spawn to a PASS.

WHAT IS NOT CLAIMED HERE
    * `mode` is not passed. `agents.list[].runtime.acp.mode` in `openclaw.json`
      is inert -- nothing reads it at spawn time -- and every session record on
      this fleet is `oneshot`. `persistent` is unreachable on this channel and
      is not chased.
    * governance. The ceiling reaches a tmux session through the hook; over ACP
      it reaches the peer only as the permission answer below, and the A-ladder
      wiring for ACP is UNPROVEN. `allow_writes` is passed explicitly rather
      than defaulted to yes.
"""
from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import time
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

#: The turn ended on its own terms.
ANSWERED = "answered"
#: The agent declined, and said why. A correct outcome.
REFUSED = "refused"
#: It attempted, and something broke.
ERRORED = "errored"
#: Nothing concluded. Neither of the above.
SILENT = "silent"
#: The session started. NOT a verdict -- see `verdict_of`.
ACCEPTED = "accepted"

# -- spawn-report statuses --------------------------------------------------
#
# A spawn that does not cleanly acknowledge collapses three DIFFERENT realities
# into one uninformative platform string ("The operation timed out"). These are
# those three, kept apart, told from one another by an actual session LOOKUP and
# never by the timeout text:
#: (a) started and still running -- the ack was merely slow.
RUNNING = "running"
#: (b) started and already finished -- it even completed.
FINISHED = "finished"
#: (c) never started -- and only ever returned on a GENUINE NEGATIVE lookup.
NEVER_STARTED = "never_started"
#: The honest fourth answer: the lookup could not be performed, so which of the
#: three this is cannot be known. This exists so `never_started` is never GUESSED
#: -- absence of evidence (no lookup, or a lookup that failed) is not a negative
#: lookup, and claiming it would rebuild the very lie this module removes.
UNKNOWN = "unknown"

#: Lookup `state` values that mean the session has already ended. Anything found
#: and not in here is, by the evidence that it EXISTS at all, still running.
_FINISHED_STATES = {"finished", "done", "complete", "completed", "ended",
                    "closed", "stopped", "exited"}

#: Where OpenClaw keeps its config on this machine.
OPENCLAW_JSON = Path(os.environ.get(
    "OPENCLAW_CONFIG", str(Path.home() / ".openclaw" / "openclaw.json")))

#: acpx ships a Claude ACP wrapper. It is not listed under
#: `plugins.entries.acpx.config.agents`, because acpx supplies it -- so the
#: lookup falls back to it BY NAME ONLY, never as a general default.
BUNDLED = {
    "claude": Path.home() / ".openclaw" / "acpx" / "claude-agent-acp-wrapper.mjs",
    "codex": Path.home() / ".openclaw" / "acpx" / "codex-acp-wrapper.mjs",
}

#: Session records live under a WORKSPACE state dir. `~/.openclaw/state/sessions`
#: is empty and has misled two separate checks; it is not this path.
SESSION_RECORDS = Path.home() / ".openclaw"


#: Live ACP connections, keyed by session name, for THIS PROCESS.
#:
#: A tmux runtime can be stateless because tmux holds the session; an ACP
#: connection is a child process this one is speaking to, so somebody has to
#: hold it. Module-level rather than per-instance because `session.runtime_for`
#: builds a fresh runtime per call — a per-instance registry would make the
#: kickoff `send` unable to find the session `assign` had just opened.
#:
#: HONEST LIMIT, stated rather than discovered later: this is process-local. A
#: later `sarsi guide` in a NEW process will not find this connection. The
#: durable handle is recorded on the task so the session can still be
#: identified; RE-ATTACHING to it across processes needs the gateway
#: (`sessions_spawn` / `sessions_yield`), which is not implemented here.
_LIVE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


class AcpUnavailable(Exception):
    """No ACP agent by that name, or no command for it. Refused rather than
    substituted: running the wrong engine under the right label is the failure
    `backends.spec_for` already refuses to commit."""


class AcpProtocolError(Exception):
    """The peer said something that is not ACP."""


class AcpTimeout(Exception):
    """The peer went quiet. Distinct from `AcpProtocolError` on purpose: a
    session that has said nothing is IDLE, and the recorded defect is exactly
    that idle and dead were reported as the same thing."""


# -- resolving the command --------------------------------------------------

def _load_config(config_path=None) -> Dict[str, Any]:
    p = Path(config_path or OPENCLAW_JSON)
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        raise AcpUnavailable(f"{p} is not there, so no ACP agent can be resolved")
    except (OSError, ValueError) as e:
        raise AcpUnavailable(f"{p} could not be read: {type(e).__name__}: {e}")


def engine_of(agent_id: str, *, config_path=None) -> str:
    """Which acpx engine an OpenClaw agent runs -- the two-hop lookup.

    `agents.list[id].runtime.acp.agent` names an ENGINE (`ai4sci`, `claude`),
    and the engine is what has a command. Skipping the hop and looking the
    agent id up directly in the acpx table is how a rename silently stops
    resolving.
    """
    cfg = _load_config(config_path)
    for entry in ((cfg.get("agents") or {}).get("list") or []):
        if (entry or {}).get("id") != agent_id:
            continue
        acp = ((entry.get("runtime") or {}).get("acp") or {})
        name = (acp.get("agent") or "").strip()
        if not name:
            raise AcpUnavailable(
                f"{agent_id} is configured, but its runtime names no ACP agent")
        return name
    raise AcpUnavailable(
        f"{agent_id} is not an ACP agent in this OpenClaw config")


def agent_command(agent_id: str, *, config_path=None) -> str:
    """The executable that speaks ACP for this agent, as a shell-free path."""
    cfg = _load_config(config_path)
    engine = engine_of(agent_id, config_path=config_path)
    table = ((((cfg.get("plugins") or {}).get("entries") or {})
              .get("acpx") or {}).get("config") or {}).get("agents") or {}
    command = ((table.get(engine) or {}).get("command") or "").strip()
    if command:
        return command
    bundled = BUNDLED.get(engine)
    if bundled and Path(bundled).exists():
        return str(bundled)
    raise AcpUnavailable(
        f"{agent_id} runs the {engine!r} ACP engine, and nothing on this "
        f"machine says how to launch it")


def agent_argv(agent_id: str, *, config_path=None) -> list:
    """The FULL invocation: the executable plus the `args` the config declares.

    An acpx entry is a command AND an argument vector, and dropping the vector
    is silent rather than loud. For `opencode` the difference decides whether
    anything works at all: bare `opencode` is `[default] = start opencode tui`,
    so on a non-TTY pipe it writes terminal-control bytes and blocks forever —
    no stdout, an EMPTY stderr, and a timeout. That reads as a hung agent, so
    the fault gets attributed to the agent instead of to the caller that never
    passed `acp`.

    Splitting the command on whitespace is NOT an acceptable substitute: it
    cannot tell an argument from a path that contains a space, and it invents
    an argv the config never asked for.
    """
    cfg = _load_config(config_path)
    engine = engine_of(agent_id, config_path=config_path)
    table = ((((cfg.get("plugins") or {}).get("entries") or {})
              .get("acpx") or {}).get("config") or {}).get("agents") or {}
    entry = table.get(engine) or {}
    command = agent_command(agent_id, config_path=config_path)
    declared = [a for a in (entry.get("args") or []) if a is not None]
    # Two shapes are in use and both have to keep working:
    #
    #   {"command": "/path/run.sh"}                 a bare launcher
    #   {"command": "/path/bin", "args": ["acp"]}   command plus a vector
    #   {"command": "/usr/bin/python /some/x.py"}   args baked into the string
    #
    # The third is the one that forces a choice. When a vector is DECLARED the
    # command is taken literally, so a launcher living under a path with a
    # space survives. When no vector is declared we keep splitting, because
    # existing configs carry their arguments inside the string and silently
    # re-interpreting those would break every one of them.
    if declared:
        argv = [command]
    else:
        argv = shlex.split(command) if " " in command else [command]
    # Coerced here rather than at the subprocess boundary: a stray number in
    # the vector should name the config that holds it, not fail deep inside
    # spawn with no idea where it came from. `None` is dropped as absent.
    argv.extend(str(a) for a in declared)
    return argv


def cwd_for(agent_id: str, *, config_path=None) -> str:
    """The working directory the config declares for this agent, if any."""
    cfg = _load_config(config_path)
    for entry in ((cfg.get("agents") or {}).get("list") or []):
        if (entry or {}).get("id") == agent_id:
            return (((entry.get("runtime") or {}).get("acp") or {})
                    .get("cwd") or "")
    return ""


# -- classifying a reply ----------------------------------------------------

def text_of(content: Any) -> str:
    """The text in an ACP content field, whatever shape it arrived in.

    THREE SHAPES, measured on real peers rather than assumed from one:
    `ai4sci-agent-acp` sends a single `{"type": "text", "text": ...}` block,
    and the bundled Claude ACP wrapper sends a LIST of blocks. Reading only the
    first shape cost a whole live `sarsi-claude` turn — the session ran, and
    the client died on `'list' object has no attribute 'get'` while the model
    was mid-answer.

    Anything that is not text (an image, a tool call) contributes nothing
    rather than a repr: this string becomes a REASON a person reads, and
    `{'type': 'image', 'data': ...}` in it is noise standing where the
    explanation should be.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(text_of(block) for block in content)
    if isinstance(content, dict):
        if content.get("type") in (None, "text"):
            return content.get("text") or ""
        # A nested content field (some peers wrap), otherwise nothing.
        inner = content.get("content")
        return text_of(inner) if inner is not None else ""
    return ""


def _error_text(err: Any) -> str:
    if isinstance(err, dict):
        msg = err.get("message") or ""
        data = err.get("data")
        return f"{msg} {data}".strip() if data else (msg or json.dumps(err))
    return str(err)


def classify(reply: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One ACP reply -> what actually happened. A pure function, on purpose:
    this is the judgement the screen-scorer got wrong, and it must be testable
    without a session, a model or a terminal."""
    reply = reply or {}
    stop = (reply.get("stop_reason") or "").strip()
    text = reply.get("text") or ""
    err = reply.get("error")

    def out(outcome, ok, attempted, refused, reason):
        return {"outcome": outcome, "ok": ok, "attempted": attempted,
                "refused": refused, "reason": reason, "text": text,
                "stop_reason": stop or None}

    if err:
        return out(ERRORED, False, True, False, _error_text(err))
    if stop == "refusal":
        # The whole point. The agent did its job; the reason is the artifact.
        return out(REFUSED, True, True, True,
                   text or "the backend refused and gave no reason")
    if stop == "end_turn":
        return out(ANSWERED, True, True, False, "")
    if stop in ("max_tokens", "max_turn_requests"):
        # Not an answer: the turn stopped because it ran out, not because it
        # was finished. Calling it ANSWERED would put a budget limit into the
        # record as a completed piece of work.
        return out(ERRORED, False, True, False,
                   f"the turn stopped at a limit ({stop}), not at an answer")
    if stop == "cancelled":
        return out(ERRORED, False, True, False,
                   "the turn was cancelled before it ended")
    if stop:
        # Unrecognised. Reported as such -- guessing which of the four it
        # resembles is how a new stop reason becomes a silent mis-verdict.
        return out(ERRORED, False, True, False,
                   f"unrecognised ACP stop reason {stop!r}")
    if text:
        return out(SILENT, False, True, False,
                   "the turn produced output but never ended")
    return out(SILENT, False, False, False,
               "no turn: the session neither answered, refused nor failed")


def verdict_of(result: Optional[Dict[str, Any]]) -> Optional[str]:
    """The verdict in a runtime result, or None when there is not one yet.

    `start` returns ACCEPTED and this returns None for it. That is the fix for
    the known consequence -- the brain's turn returns while the executor runs
    on -- expressed where a caller cannot miss it.
    """
    outcome = (result or {}).get("outcome")
    return None if outcome in (None, ACCEPTED) else outcome


# -- the wire ---------------------------------------------------------------

class StdioConnection:
    """ACP v1, newline-delimited JSON-RPC 2.0, over a child process's stdio.

    The same wire `acpx` uses; this speaks it directly so a session can be
    driven without a gateway round trip. stdout is protocol traffic only --
    the agent's own diagnostics go to stderr and are kept for the record.
    """

    def __init__(self, command: str, cwd: str, *, env=None, timeout: float = 900.0,
                 allow_writes: bool = False, stderr_path: Optional[str] = None):
        argv = list(command) if isinstance(command, (list, tuple)) else (
            shlex.split(command) if " " in command else [command])
        self.timeout = timeout
        self.allow_writes = allow_writes
        self.stderr_path = stderr_path or ""
        self._id = 0
        self._stderr = open(stderr_path, "ab") if stderr_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            argv, cwd=cwd or None, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._stderr, text=True, bufsize=1,
            env={**os.environ, **(env or {})})
        # A READER THREAD, not select() on the pipe.
        #
        # This was `select.select([self.proc.stdout], ...)` and it was WRONG in
        # a way that only a live run showed. A peer that writes its
        # `session/update` and its `session/prompt` response in one go leaves
        # both lines in the reader's own buffer after the first `readline()`;
        # `select` then asks the FILE DESCRIPTOR, which is empty, and reports
        # not-ready until the deadline. The reply was sitting in memory,
        # already read, while the client called the session IDLE.
        #
        # Measured, not reasoned about: a real ACP peer that answers
        # `stopReason: "refusal"` instantly was classified SILENT, and a live
        # `sarsi-ai4sci` turn that WROTE ITS ARTEFACT was too. Judging by the
        # artifact is what caught it -- the log said the turn had answered.
        #
        # A blocking `readline` in a thread has no second buffer to disagree
        # with, so the deadline applies to the QUEUE, which is the only place
        # a line can be waiting.
        self._lines: "queue.Queue" = queue.Queue()
        self._pump_thread = threading.Thread(target=self._pump, daemon=True)
        self._pump_thread.start()

    def _pump(self) -> None:
        try:
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    break
                self._lines.put(line)
        except Exception:
            pass
        finally:
            self._lines.put(None)          # EOF, distinct from "nothing yet"

    # -- framing
    def _write(self, msg: Dict[str, Any]) -> None:
        if self.proc.stdin is None or self.proc.poll() is not None:
            raise AcpProtocolError("the ACP agent process is gone")
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    #: What `_read` returns when the deadline passed with nothing on the wire.
    #: A distinct value, not None: "the peer closed" and "the peer went quiet"
    #: are the dead-vs-idle pair the screen-scorer could not tell apart, and
    #: returning the same thing for both would rebuild that here.
    TIMED_OUT = {"_timeout": True}

    def _read(self, deadline: Optional[float] = None) -> Optional[Dict[str, Any]]:
        # The deadline is what makes SILENT reachable at all: without it an
        # idle session is an indistinguishable hang, which is half the defect
        # this module exists to remove.
        try:
            if deadline is None:
                line = self._lines.get()
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self.TIMED_OUT
                line = self._lines.get(timeout=remaining)
        except queue.Empty:
            return self.TIMED_OUT
        if not line:
            return None
        try:
            return json.loads(line)
        except ValueError:
            # Not protocol. Skipped rather than fatal: a wrapper that prints a
            # banner should not end a session, but it must not be read as data.
            return {"_nonprotocol": line.rstrip()}

    def _answer_request(self, msg: Dict[str, Any]) -> None:
        """The peer may ask US something mid-turn. Answered explicitly.

        A permission request is answered from `allow_writes`, which the caller
        set from the ceiling. Defaulting it to yes would make ACP a way around
        the A-ladder, which is the one thing the ladder exists to prevent.
        """
        method = msg.get("method") or ""
        rid = msg.get("id")
        if method == "session/request_permission":
            options = ((msg.get("params") or {}).get("options") or [])
            want = "allow_once" if self.allow_writes else "reject_once"
            chosen = next((o.get("optionId") for o in options
                           if (o.get("kind") or o.get("optionId")) == want), None)
            if chosen is None and options:
                chosen = options[0].get("optionId") if self.allow_writes else None
            outcome = ({"outcome": "selected", "optionId": chosen} if chosen
                       else {"outcome": "cancelled"})
            self._write({"jsonrpc": "2.0", "id": rid,
                         "result": {"outcome": outcome}})
            return
        # Anything else is refused rather than approved by omission.
        self._write({"jsonrpc": "2.0", "id": rid,
                     "error": {"code": -32601,
                               "message": f"{method} is not supported by this client"}})

    def _call(self, method: str, params: Dict[str, Any],
              on_update: Optional[Callable] = None,
              timeout: Optional[float] = None) -> Dict[str, Any]:
        self._id += 1
        rid = self._id
        self._write({"jsonrpc": "2.0", "id": rid, "method": method,
                     "params": params})
        limit = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + limit if limit else None
        while True:
            msg = self._read(deadline)
            if msg is None:
                raise AcpProtocolError(
                    f"the ACP agent closed the wire during {method}")
            if msg is self.TIMED_OUT:
                raise AcpTimeout(
                    f"{method} produced nothing for {limit:g}s — the session is "
                    f"idle, which is not the same as failed")
            if "_nonprotocol" in msg:
                continue
            if msg.get("method") and msg.get("id") is not None:
                self._answer_request(msg)          # a request FROM the agent
                continue
            if msg.get("method") == "session/update":
                if on_update:
                    on_update(msg.get("params") or {})
                continue
            if msg.get("id") == rid:
                return msg

    # -- ACP
    def initialize(self) -> Dict[str, Any]:
        msg = self._call("initialize", {
            "protocolVersion": 1,
            # Declared false rather than omitted: an agent that believes the
            # client can read files for it will ask, and an unanswered ask is
            # an idle session -- the exact state nothing could diagnose before.
            "clientCapabilities": {"fs": {"readTextFile": False,
                                          "writeTextFile": False},
                                   "terminal": False}})
        return msg.get("result") or {}

    def new_session(self, cwd: str, env=None) -> str:
        msg = self._call("session/new", {"cwd": cwd, "mcpServers": []})
        if msg.get("error"):
            raise AcpProtocolError(_error_text(msg["error"]))
        sid = (msg.get("result") or {}).get("sessionId")
        if not sid:
            raise AcpProtocolError("session/new returned no sessionId")
        return sid

    def prompt(self, session_id: str, text: str) -> Dict[str, Any]:
        chunks: List[str] = []

        def collect(params):
            if not isinstance(params, dict):
                return
            chunks.append(text_of((params.get("update") or {}).get("content")))

        try:
            msg = self._call("session/prompt",
                             {"sessionId": session_id,
                              "prompt": [{"type": "text", "text": text}]},
                             on_update=collect)
        except AcpTimeout:
            # No stop reason and (usually) no text: `classify` reads that as
            # SILENT, which is the truth — nothing concluded.
            return {"text": "".join(chunks)}
        except AcpProtocolError as e:
            return {"text": "".join(chunks), "error": {"message": str(e)}}
        if msg.get("error"):
            return {"text": "".join(chunks), "error": msg["error"]}
        return {"text": "".join(chunks),
                "stop_reason": (msg.get("result") or {}).get("stopReason")}

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=15)
        except Exception:
            self.proc.kill()


def connect_stdio(*, agent_id: str, cwd: str = "", env=None,
                  config_path=None, allow_writes: bool = False,
                  timeout: float = 900.0, stderr_path=None) -> StdioConnection:
    """Spawn the ACP agent named in `openclaw.json` and speak to it.

    The peer's stderr is KEPT by default. Measured: the bundled Claude ACP
    wrapper is `#!/usr/bin/env node`, and on a PATH without node it exits
    before saying anything — over the wire that is indistinguishable from any
    other silent death, and the client can only report "closed the wire during
    initialize". The one line that says WHY (`env: 'node': No such file or
    directory`) goes to stderr, and discarding it turns a one-word fix into an
    investigation. `subprocess.DEVNULL` is available by passing
    `stderr_path=os.devnull` explicitly, which at least makes the discarding a
    decision somebody made.
    """
    command = agent_argv(agent_id, config_path=config_path)
    where = cwd or cwd_for(agent_id, config_path=config_path) or os.getcwd()
    if stderr_path is None:
        stderr_path = str(Path(where) / f".acp-{agent_id}.stderr.log")
    return StdioConnection(command, where, env=env, timeout=timeout,
                           allow_writes=allow_writes, stderr_path=stderr_path)


# -- the runtime ------------------------------------------------------------

def _last_words(conn: Any, limit: int = 400) -> str:
    """The tail of a dead peer's stderr, if it left one."""
    path = getattr(conn, "stderr_path", "")
    if not path:
        return ""
    try:
        text = Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""
    return text[-limit:]


#: Ceilings at which a session may do more than read. `A0` plans and asks.
_WRITING_CEILINGS = {"A1", "A2", "A3"}


def _default_wire():
    """The governance writer — THE SAME ONE the tmux path uses.

    Named here rather than imported at module scope so a test can see which
    writer is in force, and so this file states the rule it depends on: two
    governance writers would be two boundaries that can disagree, and the one
    that disagrees quietly is the one that stops governing.
    """
    from ai4science.harness.agents.machine.claude_driver import (
        ensure_governance_hook)
    return ensure_governance_hook


class AcpRuntime:
    """`MachineRuntime`'s interface, over ACP.

    Interchangeable with it on purpose: `session.assign` and every send/stop
    site call the same four methods, so which one drives a task is a property
    of the task's BACKEND and not a fork in the caller.
    """

    engine = "acp"

    def __init__(self, *, agent_id: str = "", connect: Optional[Callable] = None,
                 config_path=None, timeout: float = 900.0,
                 wire: Optional[Callable] = None,
                 lookup: Optional[Callable] = None):
        self.agent_id = agent_id
        self._connect = connect
        self._config_path = config_path
        self._timeout = timeout
        self._wire = wire
        # How `spawn` finds out whether a session that did not ACK is
        # nonetheless alive. `lookup(session_key)` returns a record (truthy, with
        # an optional `state`) when the session exists, a falsy value on a
        # GENUINE negative, and may raise when it simply cannot tell. Injected so
        # a test can decide the answer, and so production can point it at the
        # gateway's session listing without this file depending on the gateway.
        self._lookup = lookup

    # -- lifecycle
    def start(self, name: str, cwd: str, *, govern: bool = True,
              ceiling: str = "A0", env: Optional[Dict[str, str]] = None,
              spec: str = "", writable: Optional[List[str]] = None
              ) -> Dict[str, Any]:
        """Open the ACP session. Returns an ACCEPTANCE, never a verdict."""
        allow = (ceiling or "").strip().upper() in _WRITING_CEILINGS
        if govern:
            # BEFORE the spawn. `claude` reads project settings when the
            # session opens, so a hook written afterwards governs nothing —
            # this is the same ordering the tmux path enforces, for the same
            # reason.
            #
            # Proven on this channel before it was relied on: an acpx-spawned
            # `claude` fires the project PreToolUse hook and a non-zero exit
            # blocks the tool. The hook is a real control here, not an
            # assumption carried over from tmux.
            #
            # The declared paths travel WITH the ceiling, so the hook and the
            # sandbox draw ONE boundary rather than two that can disagree.
            try:
                (self._wire or _default_wire())(
                    cwd, ceiling=ceiling, writable=writable)
            except Exception as e:
                # NOT swallowed, and the peer is NOT spawned. `govern=True` is
                # a request to be honoured or refused, never dropped: a
                # session that cannot be governed is not the session that was
                # asked for. Returning `ok: True` here would hand every layer
                # above an ungoverned executor they believe is governed —
                # which on this channel is the ONLY boundary in force, because
                # acpx answers permission requests with `approve-all`.
                return {"ok": False, "outcome": ERRORED, "name": name,
                        "runtime": "acp", "agent_id": self.agent_id,
                        "reason": (f"could not govern the session: "
                                   f"{type(e).__name__}: {e} — not started, "
                                   f"because an ungoverned session is not the "
                                   f"one that was asked for")}
        connect = self._connect or connect_stdio
        try:
            conn = connect(agent_id=self.agent_id, cwd=cwd, env=env,
                           config_path=self._config_path, allow_writes=allow,
                           timeout=self._timeout)
        except AcpUnavailable as e:
            return {"ok": False, "outcome": ERRORED, "name": name,
                    "runtime": "acp", "reason": str(e)}
        try:
            hello = conn.initialize() or {}
            sid = conn.new_session(cwd, env)
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            # The peer's own last words, when it left any. A spawn that dies
            # before protocol has said everything it is going to say on
            # stderr, and a reason that omits it sends the reader to the wire
            # to look for something that was never on it.
            said = _last_words(conn)
            return {"ok": False, "outcome": ERRORED, "name": name,
                    "runtime": "acp", "agent_id": self.agent_id,
                    "stderr": said,
                    "reason": (f"session/new failed: {type(e).__name__}: {e}"
                               + (f" — the agent said: {said}" if said else ""))}
        with _LOCK:
            _LIVE[name] = {"conn": conn, "sid": sid, "cwd": cwd,
                           "ceiling": ceiling, "allow_writes": allow,
                           "agent_id": self.agent_id}
        return {"ok": True,
                # Accepted, not finished. `verdict_of` returns None for this.
                "outcome": ACCEPTED,
                "runtime": "acp",
                "name": name,
                "agent_id": self.agent_id,
                "acp_session_id": sid,
                "pid": getattr(getattr(conn, "proc", None), "pid", None),
                "protocol_version": hello.get("protocolVersion"),
                # Stated on the record rather than left to be assumed: every
                # session record on this fleet is oneshot, and `persistent` is
                # unreachable on this channel.
                "mode": "oneshot"}

    def spawn(self, name: str, cwd: str, **kw) -> Dict[str, Any]:
        """Spawn, and report the TRUTH from the return value alone.

        The defect this exists for: a spawn that does not cleanly acknowledge
        surfaces to the caller as one uninformative platform string ("The
        operation timed out"), which is the SAME string whether the session is
        (a) alive, (b) already finished, or (c) never created. A caller handed
        that cannot retry safely, attach, or tell a lost handle from a dead
        spawn.

        So this never propagates a bare timeout. It runs the real spawn; on a
        clean acknowledgement the session is live and it reports `RUNNING` with
        the handle. When the spawn does NOT acknowledge, it does not trust the
        error text -- it LOOKS THE SESSION UP by `name` and lets the evidence
        decide between `RUNNING`, `FINISHED` and `NEVER_STARTED`.

        The one rule that must not bend: `NEVER_STARTED` is a positive claim and
        is returned ONLY on a genuine negative lookup. With no lookup configured,
        or a lookup that itself failed, the answer is `UNKNOWN` -- never a guess
        that the session is absent. The return always carries a `session_key` so
        a follow-up can act on the handle regardless of status.
        """
        started = self.start(name, cwd, **kw)
        if started.get("ok"):
            # session/new acknowledged: the session is live and the executor
            # runs on. (Started+finished is only distinguishable via the lookup
            # path below, when the ACK itself was lost.)
            return {"status": RUNNING,
                    "session_key": name,
                    "acp_session_id": started.get("acp_session_id"),
                    "runtime": "acp",
                    "agent_id": self.agent_id,
                    "detail": "session/new acknowledged; the session is live",
                    "start": started}

        reason = started.get("reason") or "the spawn did not acknowledge"

        if self._lookup is None:
            # No way to look, so no basis for ANY of the three. Reporting
            # never_started here would be the exact lie: a positive claim with no
            # negative lookup behind it.
            return {"status": UNKNOWN, "session_key": name, "runtime": "acp",
                    "agent_id": self.agent_id,
                    "detail": (f"the spawn did not acknowledge ({reason}) and no "
                               f"session lookup is configured, so running vs "
                               f"finished vs never-started cannot be told apart")}
        try:
            found = self._lookup(name)
        except Exception as e:
            # The lookup could not answer. Still not never_started: no answer is
            # not a negative answer.
            return {"status": UNKNOWN, "session_key": name, "runtime": "acp",
                    "agent_id": self.agent_id,
                    "detail": (f"the spawn did not acknowledge ({reason}); the "
                               f"session lookup also failed "
                               f"({type(e).__name__}: {e}), so never-started "
                               f"cannot be claimed")}

        if not found:
            # A genuine negative: we asked, and there is no such session.
            return {"status": NEVER_STARTED, "session_key": name, "runtime": "acp",
                    "agent_id": self.agent_id,
                    "detail": (f"the spawn did not acknowledge ({reason}); a "
                               f"lookup for {name!r} found no session")}

        state = str((found or {}).get("state") or "").strip().lower()
        key = (found or {}).get("session_key") or name
        sid = (found or {}).get("acp_session_id")
        if state in _FINISHED_STATES:
            return {"status": FINISHED, "session_key": key, "acp_session_id": sid,
                    "runtime": "acp", "agent_id": self.agent_id,
                    "detail": (f"the spawn ack was lost ({reason}) but the "
                               f"session has already finished (state={state!r})")}
        # Found and not finished -> it exists, so it started, and it has not
        # ended: running. An unlabelled state is reported as running because the
        # session demonstrably EXISTS; that is still the started-and-live half.
        return {"status": RUNNING, "session_key": key, "acp_session_id": sid,
                "runtime": "acp", "agent_id": self.agent_id,
                "detail": (f"the spawn ack was lost ({reason}) but the session "
                           f"is live per lookup (state={state or 'unspecified'!r})")}

    def send(self, name: str, text: str, **_) -> Dict[str, Any]:
        """THE YIELD. Blocks for the turn and returns what actually happened.

        This is the half a naive caller drops. `start` returned while the
        executor ran on; without this the verdict is lost and the supervisor
        invents one from a screen.
        """
        with _LOCK:
            live = _LIVE.get(name)
        if not live:
            return dict(classify({"error": {
                "message": f"no ACP session named {name}"}}), name=name,
                runtime="acp")
        one_line = " ".join((text or "").split("\n"))
        try:
            reply = live["conn"].prompt(live["sid"], one_line)
        except Exception as e:
            reply = {"error": {"message": f"{type(e).__name__}: {e}"}}
        out = classify(reply)
        out.update({"name": name, "runtime": "acp",
                    "agent_id": self.agent_id,
                    "acp_session_id": live["sid"]})
        return out

    def stop(self, name: str) -> Dict[str, Any]:
        with _LOCK:
            live = _LIVE.pop(name, None)
        if not live:
            return {"ok": True, "name": name, "runtime": "acp",
                    "reason": "already gone"}
        try:
            live["conn"].close()
        except Exception as e:
            return {"ok": False, "name": name, "runtime": "acp",
                    "reason": f"{type(e).__name__}: {e}"}
        return {"ok": True, "name": name, "runtime": "acp"}

    def set_ceiling(self, name: str, ceiling: str) -> Dict[str, Any]:
        """A live ACP session's permission answer follows the ceiling.

        HONEST LIMIT: a tmux session's ceiling is read by the governance hook on
        every tool call, so a raise takes effect inside the running session.
        Over ACP only this client's permission answer changes -- anything the
        peer decides for itself is not governed from here. That is a real gap
        and is recorded as one rather than papered over.
        """
        with _LOCK:
            live = _LIVE.get(name)
        if not live:
            return {"ok": False, "name": name,
                    "reason": f"no ACP session named {name}"}
        allow = (ceiling or "").strip().upper() in _WRITING_CEILINGS
        live["ceiling"] = ceiling
        live["allow_writes"] = allow
        try:
            live["conn"].allow_writes = allow
        except Exception:
            pass
        return {"ok": True, "name": name, "ceiling": ceiling,
                "governs": "this client's permission answers only"}
