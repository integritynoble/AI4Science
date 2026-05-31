# Plan 3d — Harness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the robustness/correctness gaps tracked from the Plan-1 and Plan-3a reviews: restore a hard wall-clock timeout for streaming bash, add a bash-command sandbox guard, meter Anthropic input tokens, signal loop-cap truncation, and widen adapter parse coverage. These make the harness safe for headless/ensemble (Plan 2) use, not just interactive.

**Architecture:** All changes are inside the existing `ai4science/harness/` package. Bash gets a reader-thread so streaming and a hard timeout coexist (`tools/shell.py`). The `PermissionGate` gains a bash-`cmd` guard mirroring its path sandbox (`permissions.py`). The Anthropic adapter captures input tokens from the `message_start` event (`adapters/anthropic.py`). `run_loop` emits a truncation signal when it hits the iteration cap (`loop.py`). New coverage tests exercise multi-tool-call adapter streams.

**Tech Stack:** Python 3 (`subprocess`, `threading`), pytest + monkeypatch, existing `ai4science.harness`.

**Spec:** `docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md` (§11.2 Plan-3 hardening). Tracked items recorded in `docs/CLAUDE_CODE_PARITY.md` under "Plan 3d".

**Scope note:** Full OS-level bash isolation (bubblewrap/chroot) and real recorded provider stream fixtures (need live API creds) are OUT of scope — this plan does what is achievable and CI-testable. The bash-cmd guard is defense-in-depth (catches accidental + naive-adversarial touches), not airtight against deliberate shell obfuscation; that is documented.

## File structure (modified in this plan)

| File | Change |
|---|---|
| `ai4science/harness/tools/shell.py` | reader-thread streaming + hard wall-clock timeout |
| `ai4science/harness/permissions.py` | `_bash_cmd_safe` + bash branch in `allow()` |
| `ai4science/harness/adapters/anthropic.py` | capture `message_start` input tokens |
| `ai4science/harness/loop.py` | loop-cap truncation signal (for/else) |
| `tests/test_harness_*.py` | one test file per change + adapter coverage |

---

### Task 1: Hard wall-clock timeout for streaming bash (reader thread)

**Files:**
- Modify: `ai4science/harness/tools/shell.py`
- Test: `tests/test_harness_bash_timeout.py`

The Plan-3a streaming rewrite (`for line in proc.stdout`) blocks on no-output processes, so `proc.wait(timeout=...)` is never reached — a `sleep 1000` hangs forever. Fix: read stdout in a daemon thread; the main thread enforces the timeout via `proc.wait(timeout=...)` and kills on expiry (which unblocks the reader).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_bash_timeout.py
import time
from ai4science.harness.tools import shell


def test_bash_times_out_on_hang(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "BASH_TIMEOUT_SECONDS", 1)
    start = time.monotonic()
    out = shell.bash(tmp_path, cmd="sleep 30")
    elapsed = time.monotonic() - start
    assert "timed out" in out.lower()
    assert elapsed < 10           # killed promptly, not after 30s


def test_bash_still_streams_and_returns(tmp_path):
    chunks = []
    out = shell.bash(tmp_path, cmd="printf 'a\\nb\\n'", _sink=chunks.append)
    assert "a" in out and "b" in out
    assert "".join(chunks) and "".join(chunks) in out


def test_bash_nonzero_exit_preserved(tmp_path):
    out = shell.bash(tmp_path, cmd="exit 3")
    assert "exit code 3" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/spiritai/pwm/Physics_World_Model/AI4Science && python -m pytest tests/test_harness_bash_timeout.py -v`
Expected: FAIL — `test_bash_times_out_on_hang` hangs/exceeds (the current impl never times out on `sleep 30`). (It may actually hang the test; that IS the failure being fixed.)

- [ ] **Step 3: Rewrite `bash` with a reader thread**

Replace `ai4science/harness/tools/shell.py`:
```python
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

BASH_TIMEOUT_SECONDS = 300


def bash(workspace: Path, *, cmd: str, _sink: Optional[Callable[[str], None]] = None) -> str:
    """Run a shell command. Streams combined output to _sink live (if given) while
    enforcing a hard wall-clock timeout via a reader thread + proc.wait(timeout)."""
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=str(workspace),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except Exception as exc:
        return f"(failed to start: {exc})"

    buf: List[str] = []

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                buf.append(line)
                if _sink is not None:
                    _sink(line)
        except Exception:
            pass

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=BASH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        buf.append(f"\n(timed out after {BASH_TIMEOUT_SECONDS}s)")
    reader.join(timeout=5)

    out = "".join(buf)
    if proc.returncode not in (0, None):
        out += f"\n(exit code {proc.returncode})"
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_bash_timeout.py tests/test_harness_bash_stream.py tests/test_harness_tools_shell.py -v`
Expected: PASS (3 new + the Plan-3a streaming tests + Task-3-era shell tests all green). `test_bash_times_out_on_hang` now returns in ~1s.

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/tools/shell.py tests/test_harness_bash_timeout.py
git commit -m "fix(harness): restore hard bash timeout via reader thread (keeps streaming)"
```

---

### Task 2: Bash command sandbox guard

**Files:**
- Modify: `ai4science/harness/permissions.py`
- Test: `tests/test_harness_bash_sandbox.py`

The path sandbox only inspects a tool's `path` arg; `bash` uses `cmd`, so shell commands bypass the PWM moat. Add a heuristic `cmd` guard that blocks references to protected dirs and parent-escape, mirroring the path sandbox (blocks even in auto-yes mode).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_bash_sandbox.py
from ai4science.harness.permissions import PermissionGate


def _gate(tmp_path, **kw):
    return PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True, **kw)


def test_bash_blocks_protected_dir(tmp_path):
    g = _gate(tmp_path)
    ok, reason = g.allow("bash", {"cmd": "cat judge/secret.py"})
    assert ok is False and "sandbox" in reason.lower()


def test_bash_blocks_hidden_tests(tmp_path):
    ok, reason = _gate(tmp_path).allow("bash", {"cmd": "ls hidden_tests/"})
    assert ok is False and "sandbox" in reason.lower()


def test_bash_blocks_parent_escape(tmp_path):
    ok, reason = _gate(tmp_path).allow("bash", {"cmd": "cat ../../etc/passwd"})
    assert ok is False and "sandbox" in reason.lower()


def test_bash_allows_normal_command(tmp_path):
    ok, _ = _gate(tmp_path).allow("bash", {"cmd": "pytest -q && ls src"})
    assert ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_bash_sandbox.py -v`
Expected: FAIL — bash commands currently pass the sandbox.

- [ ] **Step 3: Add the bash-cmd guard**

In `ai4science/harness/permissions.py`, add a module-level helper and call it from `allow()`'s sandbox phase. Add near the top (after `PROTECTED_DIRS`):
```python
import re

_BASH_BLOCK = re.compile(
    r"(^|[\s=:/])(\.\./)"           # parent-directory escape
    r"|(^|[\s=:/'\"])(" + "|".join(PROTECTED_DIRS) + r")/"   # judge/ or hidden_tests/
)


def _bash_cmd_safe(cmd: str) -> tuple:
    """Heuristic guard: block shell commands that reference protected dirs or
    escape the workspace. NOT airtight against deliberate obfuscation (documented)."""
    if _BASH_BLOCK.search(cmd or ""):
        return False, "sandbox: bash command references a protected/parent path"
    return True, ""
```
In `allow()`, after the existing `_sandbox_ok` check and before the mutating checks, add a bash-specific branch:
```python
    def allow(self, name: str, args: Dict) -> Tuple[bool, str]:
        sok, sreason = self._sandbox_ok(name, args)
        if not sok:
            return False, sreason
        if name == "bash":
            bok, breason = _bash_cmd_safe(args.get("cmd", ""))
            if not bok:
                return False, breason
        if name not in self._mutating:
            return True, ""
        ...
```
(Keep the rest of `allow()` unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_bash_sandbox.py tests/test_harness_permissions.py -v`
Expected: PASS (4 new + existing permission tests green).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/permissions.py tests/test_harness_bash_sandbox.py
git commit -m "feat(harness): bash command sandbox guard (protected-dir/escape heuristic)"
```

---

### Task 3: Anthropic input-token metering

**Files:**
- Modify: `ai4science/harness/adapters/anthropic.py`
- Test: `tests/test_harness_adapter_anthropic.py` (add one test)

The adapter passes `input_tokens=0`, so Anthropic turns under-meter input. The `message_start` event carries `usage.input_tokens` — capture it.

- [ ] **Step 1: Write the failing test (add to the existing file)**

Append to `tests/test_harness_adapter_anthropic.py`:
```python
def test_parse_stream_captures_input_tokens_from_message_start():
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    raw = [
        _E(type="message_start", message=_E(usage=_E(input_tokens=42))),
        _E(type="content_block_delta", delta=_E(type="text_delta", text="hi")),
        _E(type="message_delta", usage=_E(output_tokens=5), delta=_E(stop_reason="end_turn")),
        _E(type="message_stop"),
    ]
    a = AnthropicAdapter()
    usages = [e for e in a._parse_stream(raw) if isinstance(e, Usage)]
    assert usages and usages[0].input == 42 and usages[0].output == 5
    assert usages[0].total == 47
```
(Ensure `Usage` is imported at the top of the test file — it already imports from `ai4science.harness.events`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_adapter_anthropic.py::test_parse_stream_captures_input_tokens_from_message_start -v`
Expected: FAIL — input is currently 0 (no message_start handling), and `_parse_stream` is called without the positional `input_tokens` (TypeError if it's required).

- [ ] **Step 3: Capture message_start usage**

In `ai4science/harness/adapters/anthropic.py`:
- Change `_parse_stream` signature default so it works without an explicit arg: `def _parse_stream(self, raw_events, input_tokens: int = 0) -> Iterator[object]:`.
- At the top of the loop body, handle `message_start`:
```python
        for ev in raw_events:
            t = getattr(ev, "type", None)
            if t == "message_start":
                input_tokens = getattr(getattr(getattr(ev, "message", None), "usage", None),
                                       "input_tokens", input_tokens)
                continue
            if t == "content_block_delta":
                ...
```
(Leave the rest of the state machine unchanged — `message_delta` already builds `Usage(input=input_tokens, output=out_toks, total=input_tokens+out_toks)`.)
- In `stream()`, change `yield from self._parse_stream(s, input_tokens=0)` to `yield from self._parse_stream(s)` (the default + message_start capture handles it).

NOTE: the existing `test_parse_stream_events` calls `a._parse_stream(raw, input_tokens=10)` with no message_start — it must still pass (input stays 10). The default-arg + message_start-override design preserves it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_adapter_anthropic.py -v`
Expected: PASS (the new test + the existing 3, including `test_parse_stream_events` which still uses input_tokens=10).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/anthropic.py tests/test_harness_adapter_anthropic.py
git commit -m "feat(harness): Anthropic input-token metering from message_start"
```

---

### Task 4: Loop-cap truncation signal

**Files:**
- Modify: `ai4science/harness/loop.py`
- Test: `tests/test_harness_loop_cap.py`

When `run_loop` exhausts `MAX_TOOL_ITERATIONS` (the model keeps requesting tools), it currently returns the accumulated text silently. Emit a truncation signal so the user/caller knows the turn was cut off.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_loop_cap.py
from pathlib import Path
from ai4science.harness import loop as loop_mod
from ai4science.harness.events import Message, ToolCall, Done
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools import default_registry


class _AlwaysToolAdapter:
    def stream(self, history, tools, *, model, reasoning):
        yield ToolCall("c1", "read", {"path": "a.py"})
        yield Done("tool_use")


def test_loop_cap_emits_truncation_signal(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x\n")
    monkeypatch.setattr(loop_mod, "MAX_TOOL_ITERATIONS", 3)
    texts = []
    history = [Message(role="user", content="go")]
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    out = loop_mod.run_loop(
        adapter=_AlwaysToolAdapter(), model="stub", reasoning="low",
        history=history, workspace=tmp_path, registry=default_registry(),
        gate=gate, on_text=texts.append, meter=lambda u: None,
    )
    assert "3 tool iterations" in out.lower() or "truncat" in out.lower()
    assert any("iteration" in t.lower() for t in texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_loop_cap.py -v`
Expected: FAIL — no truncation signal today.

- [ ] **Step 3: Add a for/else truncation note**

In `ai4science/harness/loop.py`, the loop is `for _ in range(MAX_TOOL_ITERATIONS): ... if not calls: break`. Add a `for...else` clause that runs only when the loop completes WITHOUT `break` (i.e., the cap was hit):
```python
    for _ in range(MAX_TOOL_ITERATIONS):
        ...
        if not calls:
            break
        ... (tool dispatch unchanged) ...
    else:
        note = (f"\n[harness] stopped after {MAX_TOOL_ITERATIONS} tool iterations "
                f"(possible truncation)")
        on_text(note)
        final_text_parts.append(note)

    return "".join(final_text_parts)
```
(The `else` belongs to the `for`, indented at the same level. Everything else in the loop body is unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_loop_cap.py tests/test_harness_session.py -v`
Expected: PASS (new test + existing session tests — which break out normally and never hit the else).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/loop.py tests/test_harness_loop_cap.py
git commit -m "feat(harness): signal truncation when the tool-iteration cap is hit"
```

---

### Task 5: Adapter multi-tool-call coverage

**Files:**
- Test: `tests/test_harness_adapter_coverage.py`

Widen parse coverage with synthetic streams that include MULTIPLE tool calls and interleaved text — the case most likely to regress. (Real recorded provider fixtures need live creds and are out of scope.) These tests should pass against the current adapters; if any reveals a bug, fix the adapter and note it.

- [ ] **Step 1: Write the coverage tests**

```python
# tests/test_harness_adapter_coverage.py
from ai4science.harness.events import TextDelta, ToolCall, Done
from ai4science.harness.adapters.openai import OpenAIAdapter
from ai4science.harness.adapters.gemini import GeminiAdapter


class _E:
    def __init__(self, **k): self.__dict__.update(k)


def test_openai_two_parallel_tool_calls():
    chunks = [
        _E(choices=[_E(delta=_E(content=None, tool_calls=[
            _E(index=0, id="c0", function=_E(name="read", arguments='{"path":"a"}')),
            _E(index=1, id="c1", function=_E(name="bash", arguments='{"cmd":"ls"}'))]),
            finish_reason="tool_calls")], usage=None),
    ]
    events = list(OpenAIAdapter()._parse_stream(chunks))
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert {t.name for t in tcs} == {"read", "bash"}
    assert {t.id for t in tcs} == {"c0", "c1"}


def test_gemini_text_then_two_calls():
    chunks = [
        _E(candidates=[_E(content=_E(parts=[
            _E(text="working ", function_call=None),
            _E(text=None, function_call=_E(name="read", args={"path": "a"})),
            _E(text=None, function_call=_E(name="glob", args={"pattern": "*.py"}))]))],
           usage_metadata=None),
    ]
    events = list(GeminiAdapter()._parse_stream(chunks))
    assert any(isinstance(e, TextDelta) for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert {t.name for t in tcs} == {"read", "glob"}
    assert sum(isinstance(e, Done) for e in events) == 1
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/test_harness_adapter_coverage.py -v`
Expected: PASS if the adapters handle parallel calls correctly. If a test FAILS, that's a real bug — fix the adapter (e.g., OpenAI must emit one ToolCall per `acc` slot; Gemini must emit one per `functionCall` part) and re-run until green. Document any fix in the commit message.

- [ ] **Step 3: Commit**

```bash
git add tests/test_harness_adapter_coverage.py
# include any adapter fix if a test surfaced a bug
git commit -m "test(harness): multi/parallel tool-call coverage for OpenAI + Gemini adapters"
```

---

### Task 6: Full suite green + parity doc update

- [ ] **Step 1:** Run `python -m pytest -q` — all green except the 2 pre-existing `test_list_sessions_*` env failures (`claude_agent_sdk` absent). Fix any harness regression before proceeding.
- [ ] **Step 2:** Update `docs/CLAUDE_CODE_PARITY.md`: under the Plan-3d bullet, mark these as DONE (hard bash timeout, bash-cmd sandbox guard, Anthropic input-token metering, loop-cap truncation signal, multi-tool-call coverage). Note what remains out of scope: OS-level bash isolation (bubblewrap/chroot) and real recorded provider stream fixtures (need creds).
- [ ] **Step 3:** Commit: `git commit -m "docs(parity): Plan 3d hardening landed"`.

---

## Self-review

- **Coverage:** the four tracked Plan-3d items — hard bash timeout (Task 1), bash sandbox (Task 2), Anthropic input metering (Task 3), loop-cap signal (Task 4) — each have a task; Task 5 widens adapter coverage. Out-of-scope items (OS isolation, recorded fixtures) are stated, not silently dropped.
- **Placeholder scan:** every step has concrete code. The Task-2 regex is heuristic by design and documented as such.
- **Type/consistency:** `bash(_sink=...)` signature unchanged (only the body), so `loop.run_loop`'s streaming dispatch still works; `PermissionGate.allow` keeps its `(bool, str)` contract; Anthropic `_parse_stream` gains a default arg (backward-compatible with the existing positional-call test); `run_loop` return type unchanged (str).

## Known limitations (out of scope here)
1. Bash sandbox is heuristic — a determined adversary can obfuscate (`c=judge; cat $c/x`). True isolation requires bubblewrap/chroot (future).
2. `stream()` HTTP paths remain validated by manual E2E; only synthetic fixtures are in CI.
3. The reader-thread join uses a 5s grace; a process that ignores `kill()` (uninterruptible sleep) could still delay return — acceptable, extremely rare.
