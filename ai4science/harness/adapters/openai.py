from __future__ import annotations

import json
from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done


class OpenAIAdapter(AgentAdapter):
    backend = "openai"

    def __init__(self, creds=None):
        self.creds = creds

    def _translate_tools(self, tools: List[ToolSpec]) -> list:
        return [{"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.parameters}} for t in tools]

    def _translate_messages(self, messages: List[Message]) -> list:
        out = []
        for m in messages:
            if m.role == "user" and m.images:
                content = [{"type": "text", "text": m.content}] if m.content else []
                for img in m.images:
                    content.append({"type": "image_url", "image_url": {
                        "url": f"data:{img.media_type};base64,{img.data_b64}"}})
                out.append({"role": "user", "content": content})
            elif m.role in ("system", "user"):
                out.append({"role": m.role, "content": m.content})
            elif m.role == "assistant":
                msg = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    calls = []
                    for tc in m.tool_calls:
                        d = {"id": tc.id, "type": "function",
                             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                        if tc.extra:                       # echo Gemini thought_signature etc.
                            d["extra_content"] = tc.extra
                        calls.append(d)
                    msg["tool_calls"] = calls
                out.append(msg)
            elif m.role == "tool":
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        return out

    def _usage_from(self, u) -> Usage:
        return Usage(getattr(u, "prompt_tokens", None),
                     getattr(u, "completion_tokens", None),
                     getattr(u, "total_tokens", None))

    def _parse_stream(self, chunks) -> Iterator[object]:
        acc: dict = {}   # index -> {id, name, args}
        for ch in chunks:
            # With stream_options={"include_usage": True}, OpenAI sends a final
            # chunk carrying usage with an EMPTY choices list — handle it before
            # indexing into choices[0].
            choices = getattr(ch, "choices", None) or []
            if not choices:
                u = getattr(ch, "usage", None)
                if u:
                    yield self._usage_from(u)
                continue
            choice = choices[0]
            delta = choice.delta
            if getattr(delta, "content", None):
                yield TextDelta(delta.content)
            for tcd in (getattr(delta, "tool_calls", None) or []):
                slot = acc.setdefault(tcd.index, {"id": None, "name": "", "args": "", "extra": None})
                if getattr(tcd, "id", None):
                    slot["id"] = tcd.id
                ec = getattr(tcd, "extra_content", None)   # Gemini thought_signature etc.
                if ec is not None:
                    slot["extra"] = ec.unwrap() if hasattr(ec, "unwrap") else ec
                fn = getattr(tcd, "function", None)
                if fn and getattr(fn, "name", None):
                    slot["name"] = fn.name
                if fn and getattr(fn, "arguments", None):
                    slot["args"] += fn.arguments
            if getattr(choice, "finish_reason", None):
                for slot in acc.values():
                    args = json.loads(slot["args"]) if slot["args"].strip() else {}
                    yield ToolCall(slot["id"] or "call_0", slot["name"], args,
                                   extra=slot.get("extra"))
                u = getattr(ch, "usage", None)
                if u:
                    yield self._usage_from(u)
                yield Done(choice.finish_reason)

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        if not (self.creds and self.creds.api_key):
            from ai4science.harness.events import TextDelta, Done
            yield TextDelta("[this brand has no API key configured — set the provider "
                            "key (e.g. ANTHROPIC_API_KEY / OPENAI_API_KEY) to enable it, "
                            "or use /model to switch to a reachable brand]")
            yield Done("end")
            return
        from ai4science.harness import transport
        from ai4science.harness.adapters._dotdict import dot
        c = self.creds
        headers = {"Authorization": f"Bearer {c.api_key}"}
        payload = {
            "model": model or c.model,
            "stream": True,
            "messages": self._translate_messages(messages),
            "stream_options": {"include_usage": True},
        }
        # Omit `tools` when empty — some OpenAI-compat endpoints (Gemini AI-Studio,
        # older Azure) 400 on an empty tools array.
        tool_specs = self._translate_tools(tools)
        if tool_specs:
            payload["tools"] = tool_specs
        raw = transport.sse_post(c.base_url, headers, payload)
        yield from self._parse_stream(dot(ch) for ch in raw)
