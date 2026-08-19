from __future__ import annotations

import json
from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.adapters._argsafe import loads_lenient
from ai4science.harness.events import (Message, ToolSpec, TextDelta, ToolCall,
                                        Usage, Done, ResponseMeta)


class OpenAIAdapter(AgentAdapter):
    backend = "openai"

    def __init__(self, creds=None, *, backend="openai"):
        self.creds = creds
        self.backend = backend

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
                    args = loads_lenient(slot["args"])
                    yield ToolCall(slot["id"] or "call_0", slot["name"], args,
                                   extra=slot.get("extra"))
                u = getattr(ch, "usage", None)
                if u:
                    yield self._usage_from(u)
                yield Done(choice.finish_reason)

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        if not (self.creds and self.creds.api_key):
            raise RuntimeError(f"no API key configured for {self.backend or 'openai'} backend")
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
        requested_model = payload["model"]
        yield from self._stream_with_meta(
            lambda: transport.sse_post(c.base_url, headers, payload),
            requested_model, dot)

    def _stream_with_meta(self, open_stream, requested_model, dot):
        """Emit EXACTLY ONE ResponseMeta immediately before the first semantic
        event (or at clean end-of-stream if there is none).

        Real OpenAI-compatible endpoints emit empty / metadata-less prelude
        chunks (e.g. ``{"choices": []}``) before the fields land, so metadata is
        ACCUMULATED per field across chunks: observed_model (chunk ``model``),
        system_fingerprint, and response_id (chunk ``id``) are each filled the
        FIRST time they appear and never overwritten afterwards. Absent values
        stay None — nothing is ever manufactured from the request. A failure
        (before the first chunk or mid-stream) still yields the one ResponseMeta
        with whatever has accumulated so far, then re-raises the ORIGINAL error
        unwrapped."""
        observed = {"model": None, "system_fingerprint": None, "id": None}
        emitted = False

        def _meta():
            return ResponseMeta(backend=self.backend, requested_model=requested_model,
                                observed_model=observed["model"],
                                system_fingerprint=observed["system_fingerprint"],
                                response_id=observed["id"], transport="sse")

        def _harvest():
            for ch in open_stream():
                d = dot(ch)
                for src, key in (("model", "model"),
                                 ("system_fingerprint", "system_fingerprint"),
                                 ("id", "id")):
                    if observed[key] is None:
                        observed[key] = getattr(d, src, None)
                yield d

        try:
            for ev in self._parse_stream(_harvest()):
                if not emitted:                # flush the single meta lazily,
                    emitted = True             # just before the first semantic event
                    yield _meta()
                yield ev
        except Exception:                      # first-read OR mid-stream failure
            if not emitted:
                emitted = True
                yield _meta()
            raise                              # original object, type AND message, no wrapper
        if not emitted:                        # empty / prelude-only stream: meta only
            yield _meta()
