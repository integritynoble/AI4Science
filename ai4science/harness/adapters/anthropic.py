from __future__ import annotations

import json
from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.adapters._argsafe import loads_lenient
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done


class AnthropicAdapter(AgentAdapter):
    backend = "anthropic"

    def __init__(self, creds=None):
        self.creds = creds

    def _translate_tools(self, tools: List[ToolSpec]) -> list:
        return [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools]

    def _translate_messages(self, messages: List[Message]) -> list:
        out = []
        for m in messages:
            if m.role == "user":
                if m.images:
                    blocks = [{"type": "text", "text": m.content}] if m.content else []
                    for img in m.images:
                        blocks.append({"type": "image", "source": {
                            "type": "base64", "media_type": img.media_type, "data": img.data_b64}})
                    out.append({"role": "user", "content": blocks})
                else:
                    out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                content = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content.append({"type": "tool_use", "id": tc.id,
                                    "name": tc.name, "input": tc.arguments})
                out.append({"role": "assistant", "content": content or m.content})
            elif m.role == "tool":
                out.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}]})
        return out

    def _parse_stream(self, raw_events, input_tokens: int = 0) -> Iterator[object]:
        cur_id = cur_name = None
        cur_json = ""
        for ev in raw_events:
            t = getattr(ev, "type", None)
            if t == "message_start":
                input_tokens = getattr(
                    getattr(getattr(ev, "message", None), "usage", None),
                    "input_tokens", input_tokens)
                continue
            if t == "content_block_delta":
                d = ev.delta
                if getattr(d, "type", None) == "text_delta":
                    yield TextDelta(d.text)
                elif getattr(d, "type", None) == "input_json_delta":
                    cur_json += d.partial_json
            elif t == "content_block_start":
                blk = ev.content_block
                if getattr(blk, "type", None) == "tool_use":
                    cur_id, cur_name, cur_json = blk.id, blk.name, ""
            elif t == "content_block_stop":
                if cur_id is not None:
                    args = loads_lenient(cur_json)
                    yield ToolCall(cur_id, cur_name, args)
                    cur_id = cur_name = None
                    cur_json = ""
            elif t == "message_delta":
                out_toks = getattr(getattr(ev, "usage", None), "output_tokens", None)
                yield Usage(input=input_tokens, output=out_toks,
                            total=(input_tokens + out_toks) if out_toks else None)
            elif t == "message_stop":
                yield Done()

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        if not (self.creds and self.creds.api_key):
            raise RuntimeError("no API key configured for anthropic backend")
        from ai4science.harness import transport
        from ai4science.harness.adapters._dotdict import dot
        c = self.creds
        is_oauth = getattr(c, "auth", "api_key") == "oauth"
        if is_oauth:
            # Claude Code subscription: Bearer OAuth token + the oauth beta header
            # (no x-api-key). Read the token FRESH so a background refresh is used.
            from ai4science.harness.adapters import claude_sub_creds as csc
            token = csc.subscription_token() or c.api_key or ""
            headers = {"authorization": f"Bearer {token}",
                       "anthropic-version": "2023-06-01",
                       "anthropic-beta": "oauth-2025-04-20"}
        else:
            headers = {"x-api-key": c.api_key or "", "anthropic-version": "2023-06-01"}
        sys_text = next((m.content for m in messages if m.role == "system"), None)
        payload = {
            "model": model,
            "max_tokens": 8192,
            "stream": True,
            "messages": self._translate_messages([m for m in messages if m.role != "system"]),
        }
        tool_specs = self._translate_tools(tools)
        if tool_specs:
            payload["tools"] = tool_specs
        if is_oauth:
            # OAuth (Claude Code) tokens require the Claude Code identity as the
            # leading system block; the mode's own prompt follows it.
            system_blocks = [{"type": "text",
                              "text": "You are Claude Code, Anthropic's official CLI for Claude."}]
            if sys_text:
                system_blocks.append({"type": "text", "text": sys_text})
            payload["system"] = system_blocks
        elif sys_text:
            payload["system"] = sys_text
        raw = transport.sse_post(c.base_url, headers, payload)
        yield from self._parse_stream(dot(ev) for ev in raw)
