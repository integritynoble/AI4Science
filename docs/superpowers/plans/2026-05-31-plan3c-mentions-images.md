# Plan 3c — @mentions + Image Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the last common-mode Claude-Code parity gap: **`@mentions`** (typing `@path/to/file` inlines that file's content into the turn) and **image input** (referencing an image file attaches it as a multimodal image to the turn, sent to whichever brand is driving).

**Architecture:** Built on the harness (`ai4science/harness/`). `events.py` gains an `ImagePart` type, a `Message.images` field, and a `load_image` helper. `harness/mentions.py` expands `@<path>` tokens in a line — text files are inlined, image files become `ImagePart`s. `AgentSession.run_turn` takes an optional `images=`. Each adapter's `_translate_messages` emits the brand's image block (Anthropic base64 source, OpenAI `image_url` data-URI, Gemini `inline_data`) for user messages carrying images. The REPL expands mentions per turn.

**Tech Stack:** Python 3 (`base64`, `mimetypes`, `re`), pytest + monkeypatch, existing `ai4science.harness`.

**Spec:** `docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md` (§10 Plan 3c). Predecessors: Plan 1, 3a, 3d, 3b (all merged).

**Scope note:** After this plan, common mode is at full Claude-Code parity. Image *paste from clipboard* (terminal-dependent) is out of scope — images are referenced by file path (`@image.png` or `/image <path>`).

## File structure

| File | Change |
|---|---|
| `ai4science/harness/events.py` (modify) | `ImagePart`, `Message.images`, `load_image` |
| `ai4science/harness/session.py` (modify) | `run_turn(user_input, images=None)` |
| `ai4science/harness/mentions.py` (create) | `expand(line, workspace) -> (text, images)` |
| `ai4science/harness/adapters/anthropic.py` (modify) | image blocks in `_translate_messages` |
| `ai4science/harness/adapters/openai.py` (modify) | image_url blocks |
| `ai4science/harness/adapters/gemini.py` (modify) | inline_data parts |
| `ai4science/harness/repl.py` (modify) | expand mentions per turn; `/image` |
| `tests/test_harness_*.py` | one per change |

---

### Task 1: `ImagePart` + `Message.images` + `load_image` + session threading

**Files:**
- Modify: `ai4science/harness/events.py`, `ai4science/harness/session.py`
- Test: `tests/test_harness_images_type.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_images_type.py
import base64
from pathlib import Path
from ai4science.harness.events import ImagePart, Message, load_image


def test_message_images_default():
    m = Message(role="user", content="hi")
    assert m.images == []


def test_image_part_fields():
    p = ImagePart(media_type="image/png", data_b64="AAAA")
    assert p.media_type == "image/png" and p.data_b64 == "AAAA"


def test_load_image(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")          # png magic bytes
    part = load_image(img)
    assert part.media_type == "image/png"
    assert base64.b64decode(part.data_b64) == b"\x89PNG\r\n\x1a\n"


def test_session_run_turn_attaches_images(tmp_path):
    from ai4science.harness.session import AgentSession
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.events import TextDelta, Done
    sess = AgentSession(adapter=StubAdapter([[TextDelta("ok"), Done("end")]]),
                        model="stub", backend="anthropic", workspace=tmp_path,
                        read_only=True, auto_yes=False, on_text=lambda t: None, meter=lambda u: None)
    sess.run_turn("look", images=[ImagePart("image/png", "AAAA")])
    user = [m for m in sess.history if m.role == "user"][0]
    assert user.images and user.images[0].data_b64 == "AAAA"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/spiritai/pwm/Physics_World_Model/AI4Science && python -m pytest tests/test_harness_images_type.py -v`
Expected: FAIL — `ImagePart`/`load_image` missing; `run_turn` has no `images`.

- [ ] **Step 3: Implement**

In `ai4science/harness/events.py`, add the `ImagePart` dataclass (near the others), add `images` to `Message`, and add `load_image`:
```python
@dataclass
class ImagePart:
    media_type: str          # e.g. "image/png"
    data_b64: str            # base64-encoded image bytes
```
Add to `Message` (after `tool_call_id`):
```python
    images: List["ImagePart"] = field(default_factory=list)
```
Add at the bottom of the module:
```python
def load_image(path) -> "ImagePart":
    import base64
    import mimetypes
    from pathlib import Path
    p = Path(path)
    data = p.read_bytes()
    media_type = mimetypes.guess_type(str(p))[0] or "image/png"
    return ImagePart(media_type=media_type, data_b64=base64.b64encode(data).decode("ascii"))
```

In `ai4science/harness/session.py`, change `run_turn` to accept `images`:
```python
    def run_turn(self, user_input: str, images=None) -> str:
        if self.summarize and self.compact_limit_chars:
            from ai4science.harness.compaction import maybe_compact
            self.history, _ = maybe_compact(
                self.history, limit_chars=self.compact_limit_chars, summarize=self.summarize)
        self.history.append(Message(role="user", content=user_input, images=list(images or [])))
        return run_loop(
            adapter=self.adapter, model=self.model, reasoning=self.reasoning,
            history=self.history, workspace=self.workspace, registry=self.registry,
            gate=self.gate, on_text=self.on_text, meter=self.meter,
        )
```
(Keep the `run_loop(...)` args identical to the current version — only the `Message(...)` gains `images=` and the signature gains `images=None`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_images_type.py tests/test_harness_session.py -v`
Expected: PASS (4 new + existing session tests green; existing `run_turn(x)` calls still work since `images` defaults to None).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/events.py ai4science/harness/session.py tests/test_harness_images_type.py
git commit -m "feat(harness): ImagePart + Message.images + run_turn(images=) + load_image"
```

---

### Task 2: `@mentions` expansion (text inline + image detect)

**Files:**
- Create: `ai4science/harness/mentions.py`
- Test: `tests/test_harness_mentions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_mentions.py
from ai4science.harness import mentions


def test_text_mention_inlined(tmp_path):
    (tmp_path / "note.md").write_text("hello world")
    text, images = mentions.expand("see @note.md please", tmp_path)
    assert "hello world" in text and "note.md" in text
    assert images == []


def test_image_mention_becomes_attachment(tmp_path):
    (tmp_path / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    text, images = mentions.expand("look at @p.png", tmp_path)
    assert len(images) == 1 and images[0].media_type == "image/png"
    assert "[image: p.png]" in text


def test_nonfile_mention_left_alone(tmp_path):
    text, images = mentions.expand("email @someone and @missing.txt", tmp_path)
    assert "@someone" in text and "@missing.txt" in text
    assert images == []


def test_no_mention_passthrough(tmp_path):
    text, images = mentions.expand("just a line", tmp_path)
    assert text == "just a line" and images == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_mentions.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `mentions.py`**

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from ai4science.harness.events import ImagePart, load_image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MENTION = re.compile(r"@([^\s@]+)")
_MAX_INLINE_CHARS = 50_000


def expand(line: str, workspace: Path) -> Tuple[str, List[ImagePart]]:
    """Expand @<path> tokens: inline text files, attach image files as ImageParts.
    Non-file @tokens are left untouched. Returns (rewritten_text, images)."""
    images: List[ImagePart] = []

    def _sub(m: "re.Match") -> str:
        token = m.group(1)
        p = (workspace / token)
        if not p.is_file():
            return m.group(0)
        if p.suffix.lower() in IMAGE_SUFFIXES:
            try:
                images.append(load_image(p))
            except Exception:
                return m.group(0)
            return f"[image: {token}]"
        try:
            content = p.read_text()[:_MAX_INLINE_CHARS]
        except Exception:
            return m.group(0)
        return f"\n\n--- {token} ---\n{content}\n--- end {token} ---\n"

    return _MENTION.sub(_sub, line), images
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_mentions.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/mentions.py tests/test_harness_mentions.py
git commit -m "feat(harness): @mention expansion (inline text, attach images)"
```

---

### Task 3: Anthropic adapter image translation

**Files:**
- Modify: `ai4science/harness/adapters/anthropic.py` (`_translate_messages` user branch)
- Test: `tests/test_harness_adapter_anthropic.py` (add one test)

- [ ] **Step 1: Append the failing test**

```python
def test_translate_user_message_with_image():
    from ai4science.harness.events import ImagePart
    a = AnthropicAdapter()
    msgs = [Message(role="user", content="what is this?",
                    images=[ImagePart("image/png", "AAAA")])]
    out = a._translate_messages(msgs)
    blocks = out[0]["content"]
    assert any(b.get("type") == "text" for b in blocks)
    img = [b for b in blocks if b.get("type") == "image"][0]
    assert img["source"]["type"] == "base64"
    assert img["source"]["media_type"] == "image/png" and img["source"]["data"] == "AAAA"
```

- [ ] **Step 2: Run test to verify it fails.** → FAIL (user content is a plain string today).

- [ ] **Step 3: Update the `user` branch of `_translate_messages`** in `anthropic.py`. Current:
```python
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
```
Replace with:
```python
            if m.role == "user":
                if m.images:
                    blocks = [{"type": "text", "text": m.content}] if m.content else []
                    for img in m.images:
                        blocks.append({"type": "image", "source": {
                            "type": "base64", "media_type": img.media_type, "data": img.data_b64}})
                    out.append({"role": "user", "content": blocks})
                else:
                    out.append({"role": "user", "content": m.content})
```
(Leave the assistant/tool branches unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_adapter_anthropic.py -v`
Expected: PASS (new + existing adapter tests).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/anthropic.py tests/test_harness_adapter_anthropic.py
git commit -m "feat(harness): Anthropic adapter — image blocks in user messages"
```

---

### Task 4: OpenAI adapter image translation

**Files:**
- Modify: `ai4science/harness/adapters/openai.py`
- Test: `tests/test_harness_adapter_openai.py` (add one test)

- [ ] **Step 1: Append the failing test**

```python
def test_translate_user_message_with_image():
    from ai4science.harness.events import Message, ImagePart
    a = OpenAIAdapter()
    out = a._translate_messages([Message(role="user", content="what is this?",
                                         images=[ImagePart("image/png", "AAAA")])])
    content = out[0]["content"]
    assert any(b.get("type") == "text" for b in content)
    img = [b for b in content if b.get("type") == "image_url"][0]
    assert img["image_url"]["url"] == "data:image/png;base64,AAAA"
```

- [ ] **Step 2: Run test to verify it fails.** → FAIL.

- [ ] **Step 3: Update the `system/user` branch** in `openai.py`. Current:
```python
            if m.role in ("system", "user"):
                out.append({"role": m.role, "content": m.content})
```
Replace with:
```python
            if m.role == "user" and m.images:
                content = [{"type": "text", "text": m.content}] if m.content else []
                for img in m.images:
                    content.append({"type": "image_url", "image_url": {
                        "url": f"data:{img.media_type};base64,{img.data_b64}"}})
                out.append({"role": "user", "content": content})
            elif m.role in ("system", "user"):
                out.append({"role": m.role, "content": m.content})
```
(Leave assistant/tool branches unchanged.)

- [ ] **Step 4: Run test to verify it passes.** `python -m pytest tests/test_harness_adapter_openai.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/openai.py tests/test_harness_adapter_openai.py
git commit -m "feat(harness): OpenAI adapter — image_url blocks in user messages"
```

---

### Task 5: Gemini adapter image translation

**Files:**
- Modify: `ai4science/harness/adapters/gemini.py`
- Test: `tests/test_harness_adapter_gemini.py` (add one test)

- [ ] **Step 1: Append the failing test**

```python
def test_translate_user_message_with_image():
    from ai4science.harness.events import ImagePart
    a = GeminiAdapter()
    out = a._translate_messages([Message(role="user", content="what is this?",
                                         images=[ImagePart("image/png", "AAAA")])])
    parts = out[0]["parts"]
    assert any("text" in p for p in parts)
    inline = [p for p in parts if "inline_data" in p][0]["inline_data"]
    assert inline["mime_type"] == "image/png" and inline["data"] == "AAAA"
```

- [ ] **Step 2: Run test to verify it fails.** → FAIL.

- [ ] **Step 3: Update the `user` branch** in `gemini.py`. Current:
```python
            if m.role == "user":
                out.append({"role": "user", "parts": [{"text": m.content}]})
```
Replace with:
```python
            if m.role == "user":
                parts = [{"text": m.content}] if m.content else []
                for img in m.images:
                    parts.append({"inline_data": {"mime_type": img.media_type, "data": img.data_b64}})
                out.append({"role": "user", "parts": parts})
```
(Leave model/function branches unchanged.)

- [ ] **Step 4: Run test to verify it passes.** `python -m pytest tests/test_harness_adapter_gemini.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/gemini.py tests/test_harness_adapter_gemini.py
git commit -m "feat(harness): Gemini adapter — inline_data image parts in user messages"
```

---

### Task 6: REPL wiring (@mentions per turn) + `/image` + full suite + parity doc

**Files:**
- Modify: `ai4science/harness/repl.py`
- Test: `tests/test_harness_repl_mentions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_repl_mentions.py
from ai4science.harness import repl as repl_mod
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done


def test_repl_expands_mentions_on_turn(tmp_path, monkeypatch):
    (tmp_path / "note.md").write_text("SECRET-CONTENT")
    captured = {}
    real = repl_mod.AgentSession

    def _cap(**kwargs):
        s = real(**kwargs)
        orig = s.run_turn

        def _wrapped(text, images=None):
            captured["text"] = text
            captured["images"] = images
            return orig(text, images=images)
        s.run_turn = _wrapped
        captured["session"] = s
        return s

    monkeypatch.setattr(repl_mod, "AgentSession", _cap)
    monkeypatch.setattr(repl_mod, "adapter_for",
                        lambda b: StubAdapter([[TextDelta("ok"), Done("end")]]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr("ai4science.harness.persistence.save", lambda *a, **k: None)
    inputs = iter(["summarize @note.md", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    repl_mod.run_common_repl(tmp_path, backend="anthropic", model="stub")
    assert "SECRET-CONTENT" in captured["text"]
```

- [ ] **Step 2: Run test to verify it fails.** → FAIL (mentions not expanded).

- [ ] **Step 3: Wire mention expansion into the normal-turn block** of `run_common_repl` (read the current block first). Where it currently calls `session.run_turn(line)`, change to:
```python
        # Normal turn.
        try:
            from ai4science.harness import mentions
            text, images = mentions.expand(line, workspace)
            turn_tokens["total"] = 0
            result = session.run_turn(text, images=images)
            ...
```
(Keep the rest of the block — trailing-newline print, token footer, persistence.save — unchanged.) Optionally add an inline `/image <path>` command that stages an image (`load_image`) to prepend to the next turn's images — minimal; the `@image.png` mention already covers attachment, so `/image` is a convenience and may be deferred with a note if it complicates the loop.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_repl_mentions.py tests/test_harness_repl.py tests/test_harness_repl_slash.py -v`
Expected: PASS (new + existing repl tests green).

- [ ] **Step 5: Full suite + parity doc**

Run: `python -m pytest -q` — all green except the 2 pre-existing `test_list_sessions_*` env failures. Update `docs/CLAUDE_CODE_PARITY.md`: mark Plan 3c DONE (@mentions inline text + image attach; multimodal user messages across all 3 adapters). State that common mode is now at full Claude-Code parity; clipboard image paste is out of scope (file-path images supported).

- [ ] **Step 6: Commit**

```bash
git add ai4science/harness/repl.py tests/test_harness_repl_mentions.py docs/CLAUDE_CODE_PARITY.md
git commit -m "feat(harness): expand @mentions per turn; Plan 3c parity doc"
```

---

## Self-review

- **Coverage:** ImagePart/Message.images/load_image + session threading (Task 1), @mention expansion text+image (Task 2), 3 adapter image translations (Tasks 3–5), REPL wiring (Task 6). Clipboard paste explicitly out of scope.
- **Placeholder scan:** every step has concrete code; the `/image` convenience in Task 6 is explicitly optional/deferrable, not a hidden gap.
- **Type consistency:** `Message.images: List[ImagePart]` (default []), threaded through `run_turn(images=)`; each adapter reads `img.media_type`/`img.data_b64`; `mentions.expand(line, workspace) -> (str, List[ImagePart])`. Existing `run_turn(x)` calls unaffected (images defaults None).

## Known limitations
1. Images are referenced by file path under the workspace (no clipboard paste — terminal-dependent).
2. Text mentions are truncated at 50k chars to bound context; large files are partially inlined.
3. Image size/token cost is not capped here — a per-image size guard is a future hardening item.
