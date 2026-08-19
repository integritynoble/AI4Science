"""ProxyAdapter — serve a turn through the backend LLM proxy.

Used when this machine has NO local credential for `backend` but the user has
a physicsworldmodel.org PWM token: the LLM runs on the founder's gateway and
the turn is charged to the user's PWM. Speaks the same Iterator[event]
interface as the local adapters, so the harness loop is unchanged.
"""
from __future__ import annotations

import json
from dataclasses import replace
from enum import Enum, auto
from typing import Iterator, List, Optional

from ai4science.harness import interrupt
from ai4science.harness import proxy_proto as proto
from ai4science.harness.events import Done, Message, ResponseMeta, TextDelta, ToolSpec


class _ProxyMetaPhase(Enum):
    WAITING = auto()
    EMITTED = auto()


class ProxyAdapter:
    def __init__(self, *, backend: str, base: str, token: str):
        self.backend = backend
        self.base = base.rstrip("/")
        self.token = token

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
        headers = {"Authorization": f"Bearer {self.token}",
                   "content-type": "application/json"}
        phase = _ProxyMetaPhase.WAITING

        def fallback_meta() -> ResponseMeta:
            # This describes only the local request. Provider observations stay
            # None when the proxy stream cannot supply one valid metadata event.
            return ResponseMeta(backend=self.backend, requested_model=model,
                                transport="proxy")

        try:
            with httpx.stream("POST", f"{self.base}/api/v1/llm/proxy",
                              json=body, headers=headers, timeout=600) as r:
                # Make Ctrl-C / Esc instant: while we're blocked in iter_lines()
                # (e.g. waiting on a slow first token), interrupt.request() calls
                # r.close(), which raises out of the read so the turn ends at once.
                interrupt.register_canceller(r.close)
                try:
                    if r.status_code >= 400:
                        detail = r.read().decode("utf-8", "replace")[:200]
                        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
                    for line in r.iter_lines():
                        if interrupt.requested():
                            if phase is _ProxyMetaPhase.WAITING:
                                phase = _ProxyMetaPhase.EMITTED
                                yield fallback_meta()
                            return
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except (TypeError, ValueError) as exc:
                            raise RuntimeError(
                                f"malformed proxy event: invalid JSON: {exc}") from exc
                        if not isinstance(d, dict):
                            raise RuntimeError("malformed proxy event: expected object")
                        kind = d.get("t")
                        if kind == "meta":
                            if phase is _ProxyMetaPhase.EMITTED:
                                raise RuntimeError("duplicate metadata event from proxy")
                            try:
                                ev = proto.event_from_wire(d)
                            except (TypeError, ValueError) as exc:
                                raise RuntimeError(f"malformed metadata: {exc}") from exc
                            phase = _ProxyMetaPhase.EMITTED
                            yield replace(ev, transport="proxy")
                            continue
                        if kind == "bill":
                            if phase is _ProxyMetaPhase.WAITING:
                                raise RuntimeError(
                                    "proxy stream ended without valid metadata")
                            continue            # billing handled server-side
                        ev = proto.event_from_wire(d)
                        if ev is None:
                            raise RuntimeError(
                                f"malformed proxy event: unknown type {kind!r}")
                        if phase is _ProxyMetaPhase.WAITING:
                            raise RuntimeError(
                                "proxy semantic event before metadata")
                        yield ev
                finally:
                    interrupt.unregister_canceller(r.close)
            if phase is _ProxyMetaPhase.WAITING:
                phase = _ProxyMetaPhase.EMITTED
                yield fallback_meta()
                raise RuntimeError("proxy stream ended without valid metadata")
        except RuntimeError:
            if phase is _ProxyMetaPhase.WAITING:
                phase = _ProxyMetaPhase.EMITTED
                yield fallback_meta()
            raise
        except Exception as exc:
            # A cancel (r.close from another thread) surfaces here as a read
            # error. It still exposes one None-observation metadata event, then
            # ends quietly. Genuine failures expose the same event before error.
            if phase is _ProxyMetaPhase.WAITING:
                phase = _ProxyMetaPhase.EMITTED
                yield fallback_meta()
            if interrupt.requested():
                return
            raise RuntimeError(
                f"proxy unreachable: {type(exc).__name__}: {exc}") from exc
