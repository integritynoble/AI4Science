# Plan 3e — Live Provider Wiring (SDK-free streaming) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make common mode (the native harness) *genuinely talk to LLM brands*. Verification (2026-05-31) showed the harness adapters import `anthropic`/`openai`/`google-genai` SDKs that aren't installed or declared, and aren't wired to the project's credential path — so no brand turn runs. Rewrite the adapters **SDK-free** to stream over the same REST endpoints `ai4science/llm/execute` already uses, reusing the project's credential resolvers. Result: **Gemini works immediately** (current comparegpt creds); DeepSeek/Qwen via Vertex; Anthropic/OpenAI auto-enable when an API key is present.

**Architecture:** A stdlib-`urllib` SSE transport (`harness/transport.py`); a credential resolver (`harness/adapters/creds.py`) that maps a backend to `(kind, base_url, api_key, model)` by reusing `llm/gemini.resolve_*` + `llm/openai_compat.resolve_*` (+ `ANTHROPIC_API_KEY` for anthropic); the existing adapter `_translate_*`/`_parse_stream` logic kept, but `stream()` rewritten to POST SSE and feed parsed chunks (wrapped as attribute-accessible objects) into `_parse_stream`. The OpenAI-compatible adapter serves **openai/gemini/deepseek/qwen**; the Anthropic adapter serves **anthropic** (Anthropic Messages API). The factory wires creds + reachability so the default brand is the first *reachable* one.

**Tech Stack:** Python 3 stdlib (`urllib`, `json`), pytest + monkeypatch, existing `ai4science.llm.{gemini,openai_compat,routing,user}` resolvers, existing harness adapters. **No heavy SDKs added.**

**Spec:** verification report (this session). Predecessors: Plans 1/3a/3d/3b/3c merged. This unblocks common mode AND research mode ([[project_research_mode]]).

## Grounding (from the transport investigation)
- `execute._run_anthropic`: `claude` CLI one-shot (no stream, no key visible). `_run_openai`: `codex` CLI one-shot, REST fallback if key. `_run_gemini`: `urllib`→`generativelanguage.googleapis.com/v1beta/openai/chat/completions` (comparegpt `GEMINI_API_KEY`). deepseek/qwen: `urllib`→Vertex `/endpoints/openapi/chat/completions` (gcloud token).
- Resolvers to REUSE: `gemini.resolve_base()`, `gemini.resolve_key()`; `openai_compat.resolve_base(backend)`, `openai_compat.resolve_key(backend)`, `openai_compat.default_model(backend)`. All SDK-free.
- The OpenAI-compat endpoints support `stream:true`, `tools` (function-calling), `stream_options:{include_usage:true}`.

## Decision (Director, 2026-05-31)
Wire all 3 adapter kinds SDK-free; **Gemini is the default reachable brand now**; Anthropic & OpenAI are **key-gated** (auto-enable when `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` is set, with a clear "set X to enable" message otherwise).

## File structure

| File | Change |
|---|---|
| `ai4science/harness/transport.py` (create) | `sse_post` (urllib SSE iterator) + `post_json` |
| `ai4science/harness/adapters/creds.py` (create) | `resolve(backend)`, `available(backend)` |
| `ai4science/harness/adapters/_dotdict.py` (create) | recursive attribute-accessor for SSE dicts |
| `ai4science/harness/adapters/openai.py` (modify) | `stream()` → SSE via transport+creds (serves openai/gemini/deepseek/qwen) |
| `ai4science/harness/adapters/anthropic.py` (modify) | `stream()` → SSE over `/v1/messages` |
| `ai4science/harness/adapters/factory.py` (modify) | `adapter_for(backend)` wired w/ creds; `harness_available` |
| `ai4science/harness/repl.py` (modify) | `_pick_brand` uses harness reachability (Gemini default) |
| `tests/test_harness_*.py` | per module |

---

### Task 1: SDK-free SSE transport

**Files:** Create `ai4science/harness/transport.py`; Test `tests/test_harness_transport.py`

- [ ] **Step 1: failing test**
```python
# tests/test_harness_transport.py
import io
from ai4science.harness import transport


def test_sse_post_parses_data_lines(monkeypatch):
    body = (b'data: {"a": 1}\n\n'
            b'data: {"a": 2}\n\n'
            b'data: [DONE]\n\n')

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp(body))
    chunks = list(transport.sse_post("http://x/v1/chat/completions",
                                     {"Authorization": "Bearer k"}, {"stream": True}))
    assert chunks == [{"a": 1}, {"a": 2}]


def test_post_json(monkeypatch):
    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp(b'{"ok": true}'))
    assert transport.post_json("http://x", {}, {})["ok"] is True
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement `ai4science/harness/transport.py`:
```python
from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Iterator


def _request(url: str, headers: Dict[str, str], payload: Dict[str, Any]):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", **headers}
    return urllib.request.Request(url, data=data, headers=h, method="POST")


def post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any],
              timeout: int = 120) -> Dict[str, Any]:
    with urllib.request.urlopen(_request(url, headers, payload), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sse_post(url: str, headers: Dict[str, str], payload: Dict[str, Any],
             timeout: int = 600) -> Iterator[Dict[str, Any]]:
    """POST and iterate Server-Sent-Event `data:` JSON chunks (stops at [DONE])."""
    with urllib.request.urlopen(_request(url, headers, payload), timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            body = line[len("data:"):].strip()
            if body == "[DONE]":
                break
            try:
                yield json.loads(body)
            except json.JSONDecodeError:
                continue
```

- [ ] **Step 4:** run → PASS (2). **Step 5:** commit `feat(harness): stdlib SSE transport (urllib)`.

---

### Task 2: dotdict + credential/endpoint resolver

**Files:** Create `ai4science/harness/adapters/_dotdict.py`, `ai4science/harness/adapters/creds.py`; Test `tests/test_harness_creds.py`

- [ ] **Step 1: failing test**
```python
# tests/test_harness_creds.py
from ai4science.harness.adapters import creds
from ai4science.harness.adapters._dotdict import dot


def test_dot_nested():
    o = dot({"choices": [{"delta": {"content": "hi"}}]})
    assert o.choices[0].delta.content == "hi"
    assert o.usage is None        # missing attr -> None


def test_resolve_gemini(monkeypatch):
    from ai4science.llm import gemini
    monkeypatch.setattr(gemini, "resolve_base", lambda: "https://g/v1beta/openai/")
    monkeypatch.setattr(gemini, "resolve_key", lambda: "GKEY")
    c = creds.resolve("gemini")
    assert c.kind == "openai_compat" and c.api_key == "GKEY"
    assert c.base_url.rstrip("/").endswith("openai")
    assert creds.available("gemini") is True


def test_resolve_anthropic_keyed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "AKEY")
    c = creds.resolve("anthropic")
    assert c.kind == "anthropic" and c.api_key == "AKEY"
    assert creds.available("anthropic") is True


def test_anthropic_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert creds.available("anthropic") is False
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement.

`ai4science/harness/adapters/_dotdict.py`:
```python
from __future__ import annotations


class dot:
    """Recursive attribute view over JSON (dict/list); missing attr -> None."""
    def __init__(self, data):
        self._d = data

    def __getattr__(self, name):
        if isinstance(self._d, dict):
            v = self._d.get(name)
            return dot(v) if isinstance(v, (dict, list)) else v
        return None

    def __iter__(self):
        if isinstance(self._d, list):
            for v in self._d:
                yield dot(v) if isinstance(v, (dict, list)) else v

    def __bool__(self):
        return bool(self._d)
```

`ai4science/harness/adapters/creds.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CredInfo:
    kind: str                  # "openai_compat" | "anthropic"
    base_url: str
    api_key: Optional[str]
    model: Optional[str]


def resolve(backend: str) -> CredInfo:
    if backend == "anthropic":
        return CredInfo("anthropic", "https://api.anthropic.com/v1/messages",
                        os.environ.get("ANTHROPIC_API_KEY"), None)
    if backend == "gemini":
        from ai4science.llm import gemini
        base = gemini.resolve_base().rstrip("/") + "/chat/completions"
        return CredInfo("openai_compat", base, gemini.resolve_key(), None)
    # openai / deepseek / qwen via the OpenAI-compatible resolver
    from ai4science.llm import openai_compat as oc
    base = oc.resolve_base(backend).rstrip("/") + "/chat/completions"
    return CredInfo("openai_compat", base, oc.resolve_key(backend),
                    oc.default_model(backend))


def available(backend: str) -> bool:
    try:
        c = resolve(backend)
        return bool(c.api_key and c.base_url)
    except Exception:
        return False
```

- [ ] **Step 4:** run → PASS (4). **Step 5:** commit `feat(harness): credential/endpoint resolver + dotdict (reuses llm resolvers)`.

NOTE: confirm `openai_compat.resolve_base/resolve_key/default_model` and `gemini.resolve_base/resolve_key` signatures by reading those modules first; adapt the calls if names differ.

---

### Task 3: OpenAI-compat adapter → SDK-free streaming

**Files:** Modify `ai4science/harness/adapters/openai.py`; Test `tests/test_harness_adapter_openai.py` (add a streaming test)

Keep `_translate_messages`, `_translate_tools`, `_parse_stream` (they already parse OpenAI-shaped chunk objects). Rewrite `__init__` to accept creds, and `stream()` to SSE-POST and feed dotdict-wrapped chunks to `_parse_stream`.

- [ ] **Step 1: failing test** — add:
```python
def test_openai_stream_sse_endtoend(monkeypatch):
    from ai4science.harness.adapters.openai import OpenAIAdapter
    from ai4science.harness.adapters.creds import CredInfo
    from ai4science.harness import transport
    from ai4science.harness.events import TextDelta, Done
    a = OpenAIAdapter(creds=CredInfo("openai_compat", "http://x/chat/completions", "k", "gpt-5.5"))
    sse = [{"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
           {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"total_tokens": 7}}]
    monkeypatch.setattr(transport, "sse_post", lambda *a, **k: iter(sse))
    events = list(a.stream([], [], model="gpt-5.5", reasoning="low"))
    assert any(isinstance(e, TextDelta) for e in events)
    assert any(isinstance(e, Done) for e in events)
```

- [ ] **Step 2:** run → FAIL (current stream() uses the openai SDK).
- [ ] **Step 3:** modify `openai.py`:
  - `__init__(self, creds=None)` storing `self.creds`.
  - Replace `stream()`:
```python
    def stream(self, messages, tools, *, model, reasoning):
        from ai4science.harness import transport
        from ai4science.harness.adapters._dotdict import dot
        c = self.creds
        headers = {"Authorization": f"Bearer {c.api_key}"}
        payload = {"model": model or c.model, "stream": True,
                   "messages": self._translate_messages(messages),
                   "tools": self._translate_tools(tools),
                   "stream_options": {"include_usage": True}}
        for chunk in transport.sse_post(c.base_url, headers, payload):
            yield from self._parse_stream([dot(chunk)])
```
  Note: `_parse_stream` currently consumes a full iterable and accumulates tool-call fragments across chunks. Feeding one-chunk-at-a-time breaks cross-chunk tool-call accumulation. FIX: refactor `_parse_stream` to take the whole chunk iterator (it already does) and have `stream()` pass the generator mapped through `dot`:
```python
    def stream(self, messages, tools, *, model, reasoning):
        from ai4science.harness import transport
        from ai4science.harness.adapters._dotdict import dot
        c = self.creds
        headers = {"Authorization": f"Bearer {c.api_key}"}
        payload = {"model": model or c.model, "stream": True,
                   "messages": self._translate_messages(messages),
                   "tools": self._translate_tools(tools),
                   "stream_options": {"include_usage": True}}
        raw = transport.sse_post(c.base_url, headers, payload)
        yield from self._parse_stream(dot(ch) for ch in raw)
```
  Keep `_parse_stream` UNCHANGED (it already iterates chunks and accumulates by index). The test above passes the 2-chunk list; adjust the test to call `a._parse_stream(dot(ch) for ch in sse)` OR keep the `stream()` monkeypatch form. Use the generator form so cross-chunk accumulation is preserved.

- [ ] **Step 4:** run `python -m pytest tests/test_harness_adapter_openai.py -v` → PASS (existing parse/translate tests + new streaming test). **Step 5:** commit `feat(harness): OpenAI-compat adapter streams SDK-free over SSE`.

---

### Task 4: Anthropic adapter → SDK-free streaming

**Files:** Modify `ai4science/harness/adapters/anthropic.py`; Test add a streaming test.

Keep `_translate_messages`/`_translate_tools`/`_parse_stream` (Anthropic event-shaped). Rewrite `__init__(creds=None)` + `stream()` to SSE-POST `/v1/messages`.

- [ ] **Step 1: failing test** — add:
```python
def test_anthropic_stream_sse(monkeypatch):
    from ai4science.harness.adapters.anthropic import AnthropicAdapter
    from ai4science.harness.adapters.creds import CredInfo
    from ai4science.harness import transport
    from ai4science.harness.events import TextDelta, Done
    a = AnthropicAdapter(creds=CredInfo("anthropic", "http://x/v1/messages", "k", None))
    sse = [{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}},
           {"type": "message_delta", "usage": {"output_tokens": 3}, "delta": {"stop_reason": "end_turn"}},
           {"type": "message_stop"}]
    monkeypatch.setattr(transport, "sse_post", lambda *a, **k: iter(sse))
    events = list(a.stream([], [], model="claude-opus-4-8", reasoning="high"))
    assert any(isinstance(e, TextDelta) for e in events)
    assert any(isinstance(e, Done) for e in events)
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** modify `anthropic.py`:
  - `__init__(self, creds=None)`.
  - `stream()`:
```python
    def stream(self, messages, tools, *, model, reasoning):
        from ai4science.harness import transport
        from ai4science.harness.adapters._dotdict import dot
        c = self.creds
        headers = {"x-api-key": c.api_key or "", "anthropic-version": "2023-06-01"}
        sys_text = next((m.content for m in messages if m.role == "system"), None)
        payload = {"model": model, "max_tokens": 8192, "stream": True,
                   "messages": self._translate_messages([m for m in messages if m.role != "system"]),
                   "tools": self._translate_tools(tools)}
        if sys_text:
            payload["system"] = sys_text
        raw = transport.sse_post(c.base_url, headers, payload)
        yield from self._parse_stream((dot(ev) for ev in raw))
```
  `_parse_stream` already uses `getattr(ev, "type", None)` etc. — `dot` provides attribute access (`ev.type`, `ev.delta.text`, `ev.usage.output_tokens`, `ev.message.usage.input_tokens`). Keep `_parse_stream` unchanged (it handles the message_start input-token capture from Plan 3d).

- [ ] **Step 4:** run `python -m pytest tests/test_harness_adapter_anthropic.py -v` → PASS. **Step 5:** commit `feat(harness): Anthropic adapter streams SDK-free over /v1/messages SSE`.

---

### Task 5: Factory + reachability + default brand

**Files:** Modify `ai4science/harness/adapters/factory.py`, `ai4science/harness/repl.py`; Test `tests/test_harness_factory.py` + `tests/test_harness_repl.py`

- [ ] **Step 1: failing test** — add to `tests/test_harness_factory.py`:
```python
def test_adapter_for_wires_creds(monkeypatch):
    from ai4science.harness.adapters import factory, creds
    from ai4science.harness.adapters.creds import CredInfo
    monkeypatch.setattr(creds, "resolve",
                        lambda b: CredInfo("openai_compat", "http://x/chat/completions", "k", "gpt-5.5"))
    a = factory.adapter_for("gemini")
    assert a.creds.api_key == "k"


def test_harness_available(monkeypatch):
    from ai4science.harness.adapters import factory, creds
    monkeypatch.setattr(creds, "available", lambda b: b == "gemini")
    assert factory.harness_available("gemini") is True
    assert factory.harness_available("anthropic") is False
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** modify `factory.py`:
```python
def adapter_for(backend: str):
    from ai4science.harness.adapters import creds as _creds
    c = _creds.resolve(backend)
    if c.kind == "anthropic":
        return AnthropicAdapter(creds=c)
    return OpenAIAdapter(creds=c)   # openai/gemini/deepseek/qwen all OpenAI-compat


def harness_available(backend: str) -> bool:
    from ai4science.harness.adapters import creds as _creds
    return _creds.available(backend)
```
(GeminiAdapter is no longer used by the factory — Gemini routes through the OpenAI-compat endpoint. Leave the GeminiAdapter file in place but unwired; note it in the commit.)

In `repl.py` `_pick_brand`, gate availability on `factory.harness_available` (not `routing.backend_available`, which checks the old CLI paths). The default becomes the first orchestration-chain member whose `harness_available` is True (Gemini now). When none are reachable, print a clear hint:
```python
    from ai4science.harness.adapters.factory import harness_available
    for b, m in routing.AGENT_CHAINS.get("orchestration", []):
        if harness_available(b):
            return b, m
    # nothing reachable — keep the chain default but the turn will explain how to enable
    return "gemini", "gemini-3.1-pro-preview"
```
And when a brand is selected but unavailable (e.g. anthropic w/o key), the adapter's `stream()` will fail; catch in run_loop already shows a turn error — improve the message: if `creds.api_key` is None, the adapter should immediately yield a `TextDelta` like `"[set ANTHROPIC_API_KEY to enable this brand]"` + `Done` instead of a raw error. Add that guard at the top of each `stream()`:
```python
        if not (self.creds and self.creds.api_key):
            from ai4science.harness.events import TextDelta, Done
            yield TextDelta(f"[{self.backend if hasattr(self,'backend') else 'brand'}: no API key configured — set the provider key to enable]")
            yield Done("end"); return
```
(Adapters don't currently know their backend name; pass it or use a generic message. Keep it simple.)

- [ ] **Step 4:** run `python -m pytest tests/test_harness_factory.py tests/test_harness_repl.py tests/test_harness_*.py -q` → all green. **Step 5:** commit `feat(harness): factory wires live creds; default brand = first reachable (Gemini); key-gate Anthropic/OpenAI`.

---

### Task 6: Manual E2E + verify a real Gemini turn + docs

- [ ] **Step 1:** Full suite: `python -m pytest -q` (green except the 2 pre-existing env failures).
- [ ] **Step 2: MANUAL E2E (real network, Gemini creds present):**
  ```
  printf 'read app.py and say what it does\n/exit\n' | ai4science chat --mode common --workspace <a git repo>
  ```
  Expect: streamed text from Gemini, a `read` tool call (per-edit confirm auto for read), a real answer. Capture the pane. Then `/model openai gpt-5.5` → if no key, the "[no API key]" message; with a key, a real turn.
- [ ] **Step 3:** Update `docs/CLAUDE_CODE_PARITY.md`: common mode now **runs live** — SDK-free streaming over the project's OpenAI-compat/Anthropic REST endpoints; Gemini default; Anthropic/OpenAI key-gated. Note this unblocks research mode.
- [ ] **Step 4:** commit `docs+verify: common mode runs live (Gemini default, key-gated Anthropic/OpenAI)`.

---

## Self-review
- **Coverage:** SSE transport (T1), creds+dotdict (T2), OpenAI-compat streaming (T3, serves openai/gemini/deepseek/qwen), Anthropic streaming (T4), factory/reachability/default (T5), live E2E (T6). No heavy SDKs added.
- **Placeholder scan:** Tasks 2/3 note to confirm resolver signatures by reading `llm/gemini.py`+`llm/openai_compat.py` first — a real grounding step. The `stream()` guard message is concrete.
- **Risk:** Vertex OpenAI-compat (DeepSeek/Qwen) SSE may differ from AI-Studio; if `stream:true` fails there, wrap `openai_compat.chat` (non-streaming) for those two and emit one TextDelta+Usage+Done. Gemini (AI-Studio) and OpenAI (api.openai.com) SSE are standard.

## Known limitations
1. Anthropic/OpenAI need an API key (subscription CLIs don't expose one) — by design, key-gated.
2. SSE `stream()` paths are validated by manual E2E (real network) + unit tests over canned SSE; not in CI.
3. The native `GeminiAdapter` (google-genai format) is left unwired — Gemini uses the OpenAI-compat path. Revisit if native Vertex-genai is ever wanted.
