from __future__ import annotations

import json
from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done


class AnthropicAdapter(AgentAdapter):
    backend = "anthropic"

    def _translate_tools(self, tools: List[ToolSpec]) -> list:
        return [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools]

    def _translate_messages(self, messages: List[Message]) -> list:
        out = []
        for m in messages:
            if m.role == "user":
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
                    args = json.loads(cur_json) if cur_json.strip() else {}
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
        # Thin streaming wrapper (validated manually; not in CI).
        import anthropic  # type: ignore
        client = anthropic.Anthropic()
        sys_text = next((m.content for m in messages if m.role == "system"), None)
        kwargs = dict(model=model, max_tokens=8192,
                      messages=self._translate_messages([m for m in messages if m.role != "system"]),
                      tools=self._translate_tools(tools))
        if sys_text:
            kwargs["system"] = sys_text
        with client.messages.stream(**kwargs) as s:
            yield from self._parse_stream(s)
