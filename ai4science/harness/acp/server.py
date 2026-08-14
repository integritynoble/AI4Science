"""The ACP agent half: JSON-RPC 2.0 over newline-delimited stdio.

Four methods carry a session, and they are the four implemented here:

    initialize      negotiate the protocol version and declare capabilities
    session/new     open a session bound to a working directory
    session/prompt  run one turn, streaming `session/update` notifications
    session/cancel  a NOTIFICATION — no reply, and the in-flight turn stops

Protocol version 1, matching `@agentclientprotocol/sdk` 0.21.0 as bundled with
openclaw 2026.5.12.

Three things here are deliberate rather than incidental:

* **stdout carries protocol and nothing else.** Anything a library prints to
  stdout would be parsed as a JSON-RPC frame and corrupt the stream, so stdout
  is captured for the duration of a turn and re-emitted on stderr. This is the
  single most common way a hand-written adapter fails, and it fails as a
  protocol error a long way from its cause.
* **A failing turn is a reply, not a crash.** An adapter that exits on a bad
  turn looks to the client exactly like a task that never arrived — the plan's
  own note about silent ACP write aborts. Errors come back as an
  `agent_message_chunk` plus `stopReason: "refusal"`, so the operator sees the
  reason in the transcript.
* **Cancellation is cooperative and honest.** `session/cancel` sets a flag; the
  turn in flight finishes its HTTP call and then returns `stopReason:
  "cancelled"`. It does not claim to have killed anything it did not kill.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional, TextIO

from ai4science.harness.acp import engine as _engine

PROTOCOL_VERSION = 1

#: JSON-RPC 2.0 reserved codes. Only the ones this server can actually emit.
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INTERNAL_ERROR = -32603


class _Session:
    def __init__(self, session_id: str, cwd: str) -> None:
        self.id = session_id
        self.cwd = cwd
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": _engine.system_prompt(cwd)}]
        self.cancelled = False


class ACPServer:
    """The agent side of one ACP connection.

    `out` and `inp` are injectable so the whole server can be driven in-process
    by a test over a pipe, rather than only as a spawned executable.
    """

    def __init__(self, inp: TextIO, out: TextIO, err: Optional[TextIO] = None,
                 *, complete: Optional[Callable[..., Any]] = None) -> None:
        self._in = inp
        self._out = out
        self._err = err if err is not None else sys.stderr
        self._sessions: Dict[str, _Session] = {}
        self._lock = threading.Lock()
        self._complete = complete or _engine.complete
        self._initialized = False

    # ------------------------------------------------------------- transport

    def _send(self, obj: Dict[str, Any]) -> None:
        """One frame, one line. Locked: notifications are emitted from the turn
        while a reply may be written by another path."""
        with self._lock:
            self._out.write(json.dumps(obj) + "\n")
            self._out.flush()

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _reply(self, rid: Any, result: Dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "id": rid, "result": result})

    def _error(self, rid: Any, code: int, message: str) -> None:
        self._send({"jsonrpc": "2.0", "id": rid,
                    "error": {"code": code, "message": message}})

    # ---------------------------------------------------------------- methods

    def _on_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._initialized = True
        asked = params.get("protocolVersion")
        # "The protocol version the client specified if supported by the agent,
        # or the latest protocol version supported by the agent." We support 1.
        version = PROTOCOL_VERSION if asked != PROTOCOL_VERSION else asked
        info = _engine.describe()
        from ai4science import __version__ as _v
        return {
            "protocolVersion": version,
            "agentInfo": {"name": "ai4science", "version": str(_v)},
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {"image": False, "audio": False,
                                       "embeddedContext": False},
            },
            # No auth methods: this adapter holds no credential of its own. The
            # backend's key, if it needs one, is the machine's config.
            "authMethods": [],
            "_meta": {"ai4science": info},
        }

    def _on_session_new(self, params: Dict[str, Any]) -> Dict[str, Any]:
        cwd = params.get("cwd") or os.getcwd()
        sid = "ai4sci-" + uuid.uuid4().hex[:16]
        self._sessions[sid] = _Session(sid, str(cwd))
        return {"sessionId": sid}

    def _on_session_cancel(self, params: Dict[str, Any]) -> None:
        s = self._sessions.get(params.get("sessionId") or "")
        if s is not None:
            s.cancelled = True

    def _on_session_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sid = params.get("sessionId") or ""
        session = self._sessions.get(sid)
        if session is None:
            # Not a protocol error: the client asked about a session this
            # process does not have, which happens after a restart. Say so in
            # the turn rather than killing the connection.
            return self._refuse(sid, "unknown session %r — this adapter was "
                                     "restarted and ACP has no session resume, "
                                     "so the client must open a new one" % sid)
        session.cancelled = False
        text = _prompt_text(params.get("prompt") or [])
        if not text.strip():
            return self._refuse(sid, "empty prompt")
        session.messages.append({"role": "user", "content": text})

        try:
            reply, usage = self._run_turn(session)
        except _engine.NoBackend as e:
            return self._refuse(sid, str(e))
        except Exception as e:                    # noqa: BLE001 — reported, not raised
            return self._refuse(sid, "%s: %s" % (type(e).__name__, e))

        if session.cancelled:
            return {"stopReason": "cancelled"}
        session.messages.append({"role": "assistant", "content": reply})
        self._chunk(sid, reply)
        out: Dict[str, Any] = {"stopReason": "end_turn"}
        if usage:
            out["usage"] = usage
        mid = params.get("messageId")
        if mid:
            out["userMessageId"] = mid
        return out

    def _run_turn(self, session: _Session):
        """The turn, with stdout fenced off so nothing can corrupt the stream."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            reply, usage = self._complete(session.messages)
        stray = buf.getvalue()
        if stray:
            self._err.write("[ai4science-acp] captured stray stdout: %s\n" % stray[:2000])
            self._err.flush()
        return reply, usage

    # ------------------------------------------------------------- helpers

    def _chunk(self, sid: str, text: str) -> None:
        self._notify("session/update", {
            "sessionId": sid,
            "update": {"sessionUpdate": "agent_message_chunk",
                       "content": {"type": "text", "text": text}}})

    def _refuse(self, sid: str, why: str) -> Dict[str, Any]:
        """A turn that could not run says why, in the transcript.

        `refusal` rather than `end_turn`: the client must be able to tell a
        turn that produced nothing from one that produced an answer, and a
        silent empty reply is how a broken executor passes for a working one.
        """
        if sid:
            self._chunk(sid, "ai4science could not run this turn: %s" % why)
        return {"stopReason": "refusal"}

    # ----------------------------------------------------------------- loop

    def handle(self, msg: Dict[str, Any]) -> None:
        method = msg.get("method")
        rid = msg.get("id")
        params = msg.get("params") or {}
        is_request = "id" in msg and msg["id"] is not None

        if method is None:
            if is_request:
                self._error(rid, _INVALID_REQUEST, "no method")
            return

        try:
            if method == "initialize":
                self._reply(rid, self._on_initialize(params))
            elif method == "authenticate":
                # No credential of its own to present; succeeding here is the
                # honest answer, not a stub.
                self._reply(rid, {})
            elif method == "session/new":
                self._reply(rid, self._on_session_new(params))
            elif method == "session/prompt":
                self._reply(rid, self._on_session_prompt(params))
            elif method == "session/cancel":
                self._on_session_cancel(params)      # notification: no reply
            elif is_request:
                self._error(rid, _METHOD_NOT_FOUND, "unsupported method %r" % method)
        except Exception as e:                       # noqa: BLE001
            if is_request:
                self._error(rid, _INTERNAL_ERROR, "%s: %s" % (type(e).__name__, e))
            else:
                self._err.write("[ai4science-acp] %s in %s: %s\n"
                                % (type(e).__name__, method, e))
                self._err.flush()

    def run(self) -> int:
        for line in self._in:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                self._error(None, _PARSE_ERROR, "not JSON")
                continue
            if isinstance(msg, dict):
                self.handle(msg)
        return 0


def _prompt_text(blocks: Any) -> str:
    """Flatten ACP content blocks to the text a chat backend takes.

    Text and resource_link are the baseline every agent must support; the rest
    are declared unsupported in `promptCapabilities`, so a client should not
    send them — and if one does, naming it beats dropping it silently.
    """
    if isinstance(blocks, str):
        return blocks
    out: List[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        kind = b.get("type")
        if kind == "text":
            out.append(str(b.get("text") or ""))
        elif kind == "resource_link":
            out.append("[resource: %s]" % (b.get("uri") or b.get("name") or "?"))
        elif kind == "resource":
            res = b.get("resource") or {}
            out.append(str(res.get("text") or "[resource]"))
        else:
            out.append("[unsupported content block: %s]" % kind)
    return "\n".join(p for p in out if p)


def serve(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        from ai4science import __version__ as _v
        sys.stdout.write("ai4science-acp %s (ACP protocol %d)\n"
                         % (_v, PROTOCOL_VERSION))
        return 0
    return ACPServer(sys.stdin, sys.stdout, sys.stderr).run()
