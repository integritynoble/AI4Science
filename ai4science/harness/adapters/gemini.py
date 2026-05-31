from __future__ import annotations

from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done


class GeminiAdapter(AgentAdapter):
    backend = "gemini"

    def _translate_tools(self, tools: List[ToolSpec]) -> list:
        decls = [{"name": t.name, "description": t.description, "parameters": t.parameters}
                 for t in tools]
        return [{"function_declarations": decls}] if decls else []

    def _translate_messages(self, messages: List[Message]) -> list:
        out = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "parts": [{"text": m.content}]})
            elif m.role == "assistant":
                parts = []
                if m.content:
                    parts.append({"text": m.content})
                for tc in m.tool_calls:
                    parts.append({"functionCall": {"name": tc.name, "args": tc.arguments}})
                out.append({"role": "model", "parts": parts})
            elif m.role == "tool":
                out.append({"role": "function", "parts": [
                    {"functionResponse": {"name": m.tool_call_id, "response": {"result": m.content}}}]})
        return out

    def _parse_stream(self, chunks) -> Iterator[object]:
        emitted_call = False
        for ch in chunks:
            for cand in (getattr(ch, "candidates", None) or []):
                for part in (getattr(cand.content, "parts", None) or []):
                    if getattr(part, "text", None):
                        yield TextDelta(part.text)
                    fc = getattr(part, "function_call", None)
                    if fc:
                        # Gemini has no native call id and matches tool results to
                        # calls BY FUNCTION NAME. Use the function name as the id so
                        # the loop round-trips it into functionResponse.name correctly
                        # (see _translate_messages). A synthetic "gem_<name>" id would
                        # desync the multi-turn tool loop.
                        yield ToolCall(fc.name, fc.name, dict(fc.args or {}))
                        emitted_call = True
            um = getattr(ch, "usage_metadata", None)
            if um:
                yield Usage(getattr(um, "prompt_token_count", None),
                            getattr(um, "candidates_token_count", None),
                            getattr(um, "total_token_count", None))
        yield Done("tool_use" if emitted_call else "end")

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        from google import genai  # type: ignore
        client = genai.Client()
        stream = client.models.generate_content_stream(
            model=model, contents=self._translate_messages(messages),
            config={"tools": self._translate_tools(tools)},
        )
        yield from self._parse_stream(stream)
