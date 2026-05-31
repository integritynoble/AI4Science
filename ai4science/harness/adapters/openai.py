from __future__ import annotations

import json
from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done


class OpenAIAdapter(AgentAdapter):
    backend = "openai"

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
                    msg["tool_calls"] = [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                        for tc in m.tool_calls]
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
                slot = acc.setdefault(tcd.index, {"id": None, "name": "", "args": ""})
                if getattr(tcd, "id", None):
                    slot["id"] = tcd.id
                fn = getattr(tcd, "function", None)
                if fn and getattr(fn, "name", None):
                    slot["name"] = fn.name
                if fn and getattr(fn, "arguments", None):
                    slot["args"] += fn.arguments
            if getattr(choice, "finish_reason", None):
                for slot in acc.values():
                    args = json.loads(slot["args"]) if slot["args"].strip() else {}
                    yield ToolCall(slot["id"] or "call_0", slot["name"], args)
                u = getattr(ch, "usage", None)
                if u:
                    yield self._usage_from(u)
                yield Done(choice.finish_reason)

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        from openai import OpenAI  # type: ignore
        client = OpenAI()
        stream = client.chat.completions.create(
            model=model, messages=self._translate_messages(messages),
            tools=self._translate_tools(tools), stream=True,
            stream_options={"include_usage": True},
        )
        yield from self._parse_stream(stream)
