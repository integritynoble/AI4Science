"""ProxyAdapter — serve a turn through the backend LLM proxy.

Used when this machine has NO local credential for `backend` but the user has
a physicsworldmodel.org PWM token: the LLM runs on the founder's gateway and
the turn is charged to the user's PWM. Speaks the same Iterator[event]
interface as the local adapters, so the harness loop is unchanged.
"""
from __future__ import annotations

import json
from typing import Iterator, List, Optional

from ai4science.harness import interrupt
from ai4science.harness import proxy_proto as proto
from ai4science.harness.events import Done, Message, TextDelta, ToolSpec


def _turn_cap() -> Optional[str]:
    """AI4SCIENCE_TURN_CAP_PWM: the most PWM one turn may cost. Sent as
    X-PWM-Cap; the platform charges min(usage, cap) and records the rest."""
    import os
    raw = (os.environ.get("AI4SCIENCE_TURN_CAP_PWM") or "").strip()
    return raw or None


def _session_id() -> Optional[str]:
    """AI4SCIENCE_SESSION_ID: the harness session id (repl.py's `_sid`), set
    once per process. Sent as X-PWM-Session-Id so the platform's receipt is
    bound to (payer, session, operation, request id), not the request id
    alone — a retried request id under a DIFFERENT session is a new claim,
    never answered from another session's receipt. Unset (a bare script or
    library call with no persistent session) → the platform defaults the
    session to the request id itself: one turn, its own singleton thread."""
    import os
    raw = (os.environ.get("AI4SCIENCE_SESSION_ID") or "").strip()
    return raw or None


class ProxyAdapter:
    #: The platform charges every proxied turn itself (from the gateway's
    #: `bill` line). The usage events it forwards are for display only; the
    #: client must not price them and charge the same turn again.
    bills_server_side = True

    def __init__(self, *, backend: str, base: str, token: str):
        self.backend = backend
        self.base = base.rstrip("/")
        self.token = token
        #: The platform's receipt for the last turn ({"request_id", "status",
        #: "pwm_charged", "over_cap_pwm", ...}); None before the first turn.
        #: A client that crashes can reconcile GET /api/v1/llm/receipts/{id}.
        self.last_receipt: Optional[dict] = None
        self.last_request_id: Optional[str] = None

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str = "low") -> Iterator[object]:
        import httpx
        body = {
            "backend": self.backend,
            "model": model,
            "reasoning": reasoning,
            "messages": [proto.msg_to_wire(m) for m in messages],
            "tools": [proto.tool_to_wire(t) for t in tools],
        }
        import secrets
        self.last_request_id = secrets.token_urlsafe(12)
        self.last_receipt = None
        headers = {"Authorization": f"Bearer {self.token}",
                   "content-type": "application/json",
                   # Idempotent on the platform: a retry with the same id is
                   # answered from the receipt, never served or charged twice.
                   "X-Request-Id": self.last_request_id}
        cap = _turn_cap()
        if cap:
            headers["X-PWM-Cap"] = cap
        session_id = _session_id()
        if session_id:
            headers["X-PWM-Session-Id"] = session_id
        try:
            with httpx.stream("POST", f"{self.base}/api/v1/llm/proxy",
                              json=body, headers=headers, timeout=600) as r:
                # Make Ctrl-C / Esc instant: while we're blocked in iter_lines()
                # (e.g. waiting on a slow first token), interrupt.request() calls
                # r.close(), which raises out of the read so the turn ends at once
                # instead of waiting for the next line. Poll the flag too, in case
                # the close races a line that already arrived.
                interrupt.register_canceller(r.close)
                try:
                    if r.status_code >= 400:
                        detail = r.read().decode("utf-8", "replace")[:200]
                        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
                    for line in r.iter_lines():
                        if interrupt.requested():
                            return
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if d.get("t") == "bill":
                            continue            # billing handled server-side
                        if d.get("t") == "receipt":
                            self.last_receipt = d   # the platform's word, kept for /cost
                            continue
                        ev = proto.event_from_wire(d)
                        if ev is not None:
                            yield ev
                finally:
                    interrupt.unregister_canceller(r.close)
        except RuntimeError:
            raise               # re-raise our own HTTP-status errors (triggers fallback)
        except Exception as exc:
            # A cancel (r.close from another thread) surfaces here as a read
            # error — that's intentional, so end quietly instead of showing a
            # scary "[proxy unreachable]". Only report genuine failures.
            if interrupt.requested():
                return
            raise RuntimeError(f"proxy unreachable: {type(exc).__name__}: {exc}")
