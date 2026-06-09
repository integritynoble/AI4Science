from __future__ import annotations

import json
import uuid
from typing import Iterator, List, Tuple

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.adapters._argsafe import loads_lenient
from ai4science.harness.adapters import codex_creds
from ai4science.harness.events import (Message, ToolSpec, TextDelta, ToolCall,
                                       Usage, Done)
from ai4science.harness import transport

# The ChatGPT-subscription codex backend speaks the Responses API over OAuth.
_URL = "https://chatgpt.com/backend-api/codex/responses"
_VERSION = "0.135.0"


class CodexAdapter(AgentAdapter):
    """OpenAI via the codex/ChatGPT OAuth subscription (Responses API streaming).

    Used when `~/.codex/auth.json` has a chatgpt login — the api-key path 401s in
    this deployment, so this is how openai actually runs in the harness.
    """

    backend = "openai"

    def _translate_tools(self, tools: List[ToolSpec]) -> list:
        return [{"type": "function", "name": t.name, "description": t.description,
                 "parameters": t.parameters, "strict": False} for t in tools]

    def _translate_input(self, messages: List[Message]) -> Tuple[str, list]:
        """Return (instructions, input_items) for the Responses API."""
        instr: List[str] = []
        items: list = []
        for m in messages:
            if m.role == "system":
                if m.content:
                    instr.append(m.content)
            elif m.role == "user":
                content = [{"type": "input_text", "text": m.content or ""}]
                for img in (m.images or []):
                    content.append({"type": "input_image",
                                    "image_url": f"data:{img.media_type};base64,{img.data_b64}"})
                items.append({"type": "message", "role": "user", "content": content})
            elif m.role == "assistant":
                if m.content:
                    items.append({"type": "message", "role": "assistant",
                                  "content": [{"type": "output_text", "text": m.content}]})
                for tc in (m.tool_calls or []):
                    items.append({"type": "function_call", "call_id": tc.id,
                                  "name": tc.name,
                                  "arguments": json.dumps(tc.arguments)})
            elif m.role == "tool":
                items.append({"type": "function_call_output",
                              "call_id": m.tool_call_id, "output": m.content or ""})
        return ("\n\n".join(instr), items)

    def _parse_stream(self, chunks) -> Iterator[object]:
        for c in chunks:
            t = c.get("type") if isinstance(c, dict) else None
            if t == "response.output_text.delta":
                d = c.get("delta")
                if d:
                    yield TextDelta(d)
            elif t == "response.output_item.done":
                item = c.get("item") or {}
                if item.get("type") == "function_call":
                    yield ToolCall(item.get("call_id") or "call_0",
                                   item.get("name") or "",
                                   loads_lenient(item.get("arguments") or ""))
            elif t == "response.completed":
                resp = c.get("response") or {}
                u = resp.get("usage") or {}
                if u:
                    inp, out = u.get("input_tokens"), u.get("output_tokens")
                    total = u.get("total_tokens")
                    if total is None:
                        total = (inp or 0) + (out or 0)
                    yield Usage(inp, out, total)
                yield Done(resp.get("status") or "completed")
            elif t == "response.failed":
                resp = c.get("response") or {}
                err = (resp.get("error") or {}).get("message") or "response.failed"
                raise RuntimeError(f"codex backend: {err}")

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str = "medium") -> Iterator[object]:
        if not codex_creds.codex_available():
            yield TextDelta("[codex] no ChatGPT subscription — run `codex login`.")
            yield Done("error")
            return
        if codex_creds.codex_token_expired():
            yield TextDelta("[codex] login expired — refresh it: run `codex exec "
                            "\"ok\"` (or `codex login`) to renew the token, then retry.")
            yield Done("error")
            return
        tok, acct = codex_creds.codex_auth()
        instructions, items = self._translate_input(messages)
        payload = {
            "model": model,
            "instructions": instructions,
            "input": items,
            "tools": self._translate_tools(tools),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "store": False,
            "stream": True,
        }
        if reasoning:
            payload["reasoning"] = {"effort": reasoning}
        headers = {
            "Authorization": f"Bearer {tok}",
            "chatgpt-account-id": acct,
            "Accept": "text/event-stream",
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "session_id": str(uuid.uuid4()),
            "User-Agent": f"codex_cli_rs/{_VERSION}",
        }
        yield from self._parse_stream(transport.sse_post(_URL, headers, payload))
