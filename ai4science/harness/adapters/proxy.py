"""ProxyAdapter — serve a turn through the backend LLM proxy.

Used when this machine has NO local credential for `backend` but the user has
a physicsworldmodel.org PWM token: the LLM runs on the founder's gateway and
the turn is charged to the user's PWM. Speaks the same Iterator[event]
interface as the local adapters, so the harness loop is unchanged.
"""
from __future__ import annotations

import json
from typing import Iterator, List, Optional

from ai4science.harness import proxy_proto as proto
from ai4science.harness.events import Done, Message, TextDelta, ToolSpec


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
        try:
            with httpx.stream("POST", f"{self.base}/api/v1/llm/proxy",
                              json=body, headers=headers, timeout=600) as r:
                if r.status_code >= 400:
                    detail = r.read().decode("utf-8", "replace")[:200]
                    yield TextDelta(f"[proxy {r.status_code}: {detail}]")
                    yield Done("error")
                    return
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("t") == "bill":
                        continue            # billing handled server-side
                    ev = proto.event_from_wire(d)
                    if ev is not None:
                        yield ev
        except Exception as exc:
            yield TextDelta(f"[proxy unreachable: {type(exc).__name__}: {exc}]")
            yield Done("error")
