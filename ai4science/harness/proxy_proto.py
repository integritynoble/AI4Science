"""Wire protocol for the LLM proxy — shared by the host gateway (server) and
the CLI ProxyAdapter (client). JSONL: one JSON object per line.

Lets a remote user with only a PWM token use the founder-served LLMs: the CLI
serializes (messages, tools) → the backend forwards → the host gateway runs the
real harness adapter with the founder credentials → events stream back.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ai4science.harness.events import (Done, Message, ResponseMeta, TextDelta,
                                       ToolCall, ToolSpec, Usage)


# ── request: messages + tools → wire dicts and back ────────────────────────

def msg_to_wire(m: Message) -> Dict[str, Any]:
    return {
        "role": m.role,
        "content": m.content,
        "tool_calls": [{"id": t.id, "name": t.name, "arguments": t.arguments,
                        "extra": t.extra} for t in (m.tool_calls or [])],
        "tool_call_id": getattr(m, "tool_call_id", None),
        # images are dropped over the proxy (v1: text + tools only)
    }


def msg_from_wire(d: Dict[str, Any]) -> Message:
    tcs = [ToolCall(id=t.get("id", ""), name=t.get("name", ""),
                    arguments=t.get("arguments") or {}, extra=t.get("extra"))
           for t in (d.get("tool_calls") or [])]
    return Message(role=d.get("role", "user"), content=d.get("content") or "",
                   tool_calls=tcs, tool_call_id=d.get("tool_call_id"))


def tool_to_wire(t: ToolSpec) -> Dict[str, Any]:
    return {"name": t.name, "description": t.description, "parameters": t.parameters}


def tool_from_wire(d: Dict[str, Any]) -> ToolSpec:
    return ToolSpec(name=d["name"], description=d.get("description", ""),
                    parameters=d.get("parameters") or {})


# ── response events → wire dicts and back ──────────────────────────────────

def event_to_wire(ev: object) -> Dict[str, Any]:
    if isinstance(ev, ResponseMeta):
        return {
            "t": "meta",
            "backend": ev.backend,
            "requested_model": ev.requested_model,
            "observed_model": ev.observed_model,
            "system_fingerprint": ev.system_fingerprint,
            "response_id": ev.response_id,
            "transport": ev.transport,
        }
    if isinstance(ev, TextDelta):
        return {"t": "text", "text": ev.text}
    if isinstance(ev, ToolCall):
        return {"t": "tool", "id": ev.id, "name": ev.name,
                "arguments": ev.arguments, "extra": ev.extra}
    if isinstance(ev, Usage):
        return {"t": "usage", "input": ev.input, "output": ev.output, "total": ev.total}
    if isinstance(ev, Done):
        return {"t": "done", "stop_reason": ev.stop_reason}
    return {"t": "ignore"}


_META_FIELDS = frozenset({
    "backend", "requested_model", "observed_model",
    "system_fingerprint", "response_id", "transport",
})


def response_meta_from_wire(d: Dict[str, Any]) -> ResponseMeta:
    missing = _META_FIELDS.difference(d)
    if missing:
        raise ValueError(f"missing fields: {', '.join(sorted(missing))}")
    for field in ("backend", "requested_model", "transport"):
        value = d[field]
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be a non-empty string")
    for field in ("observed_model", "system_fingerprint", "response_id"):
        value = d[field]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} must be a string or null")
    return ResponseMeta(
        backend=d["backend"],
        requested_model=d["requested_model"],
        observed_model=d["observed_model"],
        system_fingerprint=d["system_fingerprint"],
        response_id=d["response_id"],
        transport=d["transport"],
    )


def event_from_wire(d: Dict[str, Any]) -> object:
    k = d.get("t")
    if k == "meta":
        return response_meta_from_wire(d)
    if k == "text":
        return TextDelta(d.get("text", ""))
    if k == "tool":
        return ToolCall(id=d.get("id", ""), name=d.get("name", ""),
                        arguments=d.get("arguments") or {}, extra=d.get("extra"))
    if k == "usage":
        return Usage(input=d.get("input"), output=d.get("output"), total=d.get("total"))
    if k == "done":
        return Done(d.get("stop_reason"))
    return None
