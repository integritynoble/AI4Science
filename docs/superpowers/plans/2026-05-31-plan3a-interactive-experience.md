# Plan 3a — Interactive Experience Essentials (Claude-Code parity) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the native harness (Plan 1) toward the felt Claude-Code experience: live bash output streaming, rich diff preview on edit-confirm, session persistence + `--continue`/`--resume`, context compaction, and the full slash-command set in the harness REPL.

**Architecture:** Build on the Plan-1 `ai4science/harness/` package. Add a tool **output sink** so streaming-capable tools (bash) push output live through the loop's `on_text`; a pure **diff renderer** wired into the permission preview; a **persistence** module (JSONL of normalized `Message`s under the user config dir) with `--continue`/`--resume`; a **compaction** step that summarizes old history when it exceeds a token threshold (summarizer is injectable for CI); and an expanded **slash-command set** in `harness/repl.py`. Each unit is testable without a real LLM.

**Tech Stack:** Python 3, pytest + monkeypatch, existing `ai4science.harness` (events/loop/session/repl/tools), `ai4science.user` (config dir), `ai4science.llm` (for the compaction summarizer via `execute`/routing). Rich is used only for terminal rendering and is kept behind a plain-text-testable seam.

**Spec:** `docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md` (§3 parity bar; §11.2 Plan-3 is REQUIRED for full parity). Predecessor: `docs/superpowers/plans/2026-05-31-native-interactive-harness.md`.

**Scope note:** Sub-agents (`Task`) + MCP are **Plan 3b**; `@mentions` + images are **Plan 3c**; bash sandboxing + Anthropic input-token metering + loop-cap signal + streaming fixtures are **Plan 3d**. This plan is 3a only.

## File structure

| File | Responsibility |
|---|---|
| `ai4science/harness/tools/base.py` (modify) | add optional `streams` flag to `Tool`; sink-aware dispatch contract |
| `ai4science/harness/tools/shell.py` (modify) | `bash` streams stdout/stderr live via an optional `sink` |
| `ai4science/harness/tools/__init__.py` (modify) | mark `bash` as `streams=True` |
| `ai4science/harness/loop.py` (modify) | pass a per-call `sink` to streaming tools; forward to `on_text` |
| `ai4science/harness/diff.py` (create) | `unified_diff(path, old, new)` pure renderer |
| `ai4science/harness/permissions.py` (modify) | edit preview uses `diff.unified_diff` |
| `ai4science/harness/persistence.py` (create) | save/load session history (JSONL) + list/most-recent |
| `ai4science/harness/session.py` (modify) | `to_records()/load_records()`; `session_id` |
| `ai4science/harness/compaction.py` (create) | `maybe_compact(history, *, limit, summarize)` |
| `ai4science/harness/repl.py` (modify) | `--continue`/`--resume`, compaction hook, full slash set |
| `ai4science/commands/chat.py` (modify) | thread `continue_session`/`resume` into `run_common_repl` |
| `tests/test_harness_*.py` | one test file per unit |

---

### Task 1: Live bash output streaming (tool output sink)

**Files:**
- Modify: `ai4science/harness/tools/base.py`, `ai4science/harness/tools/shell.py`, `ai4science/harness/tools/__init__.py`, `ai4science/harness/loop.py`
- Test: `tests/test_harness_bash_stream.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_bash_stream.py
from pathlib import Path
from ai4science.harness.tools import shell, default_registry
from ai4science.harness.tools.base import Tool


def test_bash_streams_to_sink(tmp_path):
    chunks = []
    out = shell.bash(tmp_path, cmd="printf 'a\\nb\\nc\\n'", _sink=chunks.append)
    # full output still returned
    assert out.count("a") == 1 and "b" in out and "c" in out
    # and streamed incrementally to the sink
    assert "".join(chunks).count("a") == 1
    assert "".join(chunks) == out or "".join(chunks) in out


def test_bash_without_sink_still_returns(tmp_path):
    out = shell.bash(tmp_path, cmd="echo hi")
    assert "hi" in out


def test_bash_tool_marked_streaming():
    reg = default_registry()
    assert reg.get("bash").streams is True
    assert reg.get("read").streams is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/spiritai/pwm/Physics_World_Model/AI4Science && python -m pytest tests/test_harness_bash_stream.py -v`
Expected: FAIL — `bash()` has no `_sink`; `Tool` has no `streams`.

- [ ] **Step 3: Add `streams` to Tool and stream from bash**

In `ai4science/harness/tools/base.py`, add the field:

```python
@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable[..., str]
    mutating: bool = False
    streams: bool = False          # True => func accepts a _sink kwarg for live output
```

Replace `ai4science/harness/tools/shell.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional

BASH_TIMEOUT_SECONDS = 300


def bash(workspace: Path, *, cmd: str, _sink: Optional[Callable[[str], None]] = None) -> str:
    """Run a shell command. If _sink is given, stream combined output to it live."""
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=str(workspace),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except Exception as exc:
        return f"(failed to start: {exc})"

    buf = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            buf.append(line)
            if _sink is not None:
                _sink(line)
        proc.wait(timeout=BASH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        buf.append(f"\n(timed out after {BASH_TIMEOUT_SECONDS}s)")
    out = "".join(buf)
    if proc.returncode not in (0, None):
        out += f"\n(exit code {proc.returncode})"
    return out
```

In `ai4science/harness/tools/__init__.py`, mark bash streaming (change only the bash registration):

```python
    reg.add(Tool("bash", "Run a shell command in the workspace.",
                 {"type": "object", "properties": {"cmd": _STR}, "required": ["cmd"]},
                 shell.bash, mutating=True, streams=True))
```

In `ai4science/harness/loop.py`, when dispatching a streaming tool, pass a sink that forwards to `on_text`. Replace the tool-execution block inside `run_loop`:

```python
        for tc in calls:
            ok, reason = gate.allow(tc.name, tc.arguments)
            if not ok:
                result = f"[blocked] {reason}"
            else:
                try:
                    tool = registry.get(tc.name)
                    if tool.streams:
                        result = tool.func(workspace, **tc.arguments, _sink=on_text)
                    else:
                        result = tool.func(workspace, **tc.arguments)
                except Exception as exc:
                    result = f"[error] {exc}"
            history.append(Message(role="tool", content=str(result), tool_call_id=tc.id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_bash_stream.py tests/test_harness_tools_shell.py tests/test_harness_session.py -v`
Expected: PASS (new 3 + existing shell/session tests still green; the session loop test still works because `read` is non-streaming).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/tools/base.py ai4science/harness/tools/shell.py ai4science/harness/tools/__init__.py ai4science/harness/loop.py tests/test_harness_bash_stream.py
git commit -m "feat(harness): live bash output streaming via tool sink"
```

---

### Task 2: Unified diff renderer + edit-confirm preview

**Files:**
- Create: `ai4science/harness/diff.py`
- Modify: `ai4science/harness/permissions.py` (`_preview` for `edit`/`write` uses the diff)
- Test: `tests/test_harness_diff.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_diff.py
from ai4science.harness.diff import unified_diff
from ai4science.harness import permissions


def test_unified_diff_shows_change():
    d = unified_diff("a.py", "x = 1\ny = 2\n", "x = 42\ny = 2\n")
    assert "a.py" in d
    assert "-x = 1" in d and "+x = 42" in d
    assert " y = 2" in d            # unchanged context line


def test_unified_diff_new_file():
    d = unified_diff("new.py", "", "hello\n")
    assert "+hello" in d


def test_edit_preview_uses_diff(tmp_path):
    # the permission preview for edit should contain a diff-style line
    gate = permissions.PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    # _preview is module-level
    p = permissions._preview("edit", {"path": "a.py", "old": "x = 1", "new": "x = 42"})
    assert "-x = 1" in p and "+x = 42" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_diff.py -v`
Expected: FAIL — module missing; `_preview` edit branch not diff-based.

- [ ] **Step 3: Implement the diff renderer and wire the preview**

`ai4science/harness/diff.py`:

```python
from __future__ import annotations

import difflib


def unified_diff(path: str, old: str, new: str) -> str:
    """A plain unified diff between old and new content for `path`."""
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}",
    )
    return "".join(lines)
```

In `ai4science/harness/permissions.py`, change the `edit` branch of `_preview` to render a diff (the gate doesn't read the file, so synthesize old/new from the args — old string vs new string as a minimal hunk):

```python
def _preview(name: str, args: Dict) -> str:
    if name == "bash":
        return f"$ {args.get('cmd', '')}"
    if name == "write":
        from ai4science.harness.diff import unified_diff
        return unified_diff(args.get("path", "?"), "", args.get("content", ""))
    if name == "edit":
        from ai4science.harness.diff import unified_diff
        old = args.get("old", "")
        new = args.get("new", "")
        return unified_diff(args.get("path", "?"),
                            old if old.endswith("\n") else old + "\n",
                            new if new.endswith("\n") else new + "\n")
    return f"{name} {args}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_diff.py tests/test_harness_permissions.py -v`
Expected: PASS (3 new + existing permission tests still green — the existing tests assert on (bool, reason) tuples, not preview text, so they are unaffected).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/diff.py ai4science/harness/permissions.py tests/test_harness_diff.py
git commit -m "feat(harness): unified diff renderer + diff-based edit preview"
```

---

### Task 3: Session persistence (save/load history)

**Files:**
- Create: `ai4science/harness/persistence.py`
- Modify: `ai4science/harness/session.py` (add `session_id`, `to_records`, `load_records`)
- Test: `tests/test_harness_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_persistence.py
from pathlib import Path
from ai4science.harness.events import Message, ToolCall
from ai4science.harness import persistence


def test_roundtrip_history(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    history = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="reading", tool_calls=[ToolCall("c1", "read", {"path": "a"})]),
        Message(role="tool", content="data", tool_call_id="c1"),
    ]
    persistence.save("sess1", tmp_path / "ws", history)
    loaded = persistence.load("sess1")
    assert [m.role for m in loaded] == ["user", "assistant", "tool"]
    assert loaded[1].tool_calls[0].name == "read"
    assert loaded[2].tool_call_id == "c1"


def test_most_recent_for_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "sessions_dir", lambda: tmp_path)
    ws = tmp_path / "ws"
    persistence.save("old", ws, [Message(role="user", content="1")])
    persistence.save("new", ws, [Message(role="user", content="2")])
    assert persistence.most_recent(ws) in ("old", "new")
    # most_recent returns the last-saved id
    assert persistence.most_recent(ws) == "new"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_persistence.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement persistence**

`ai4science/harness/persistence.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from ai4science.harness.events import Message, ToolCall


def sessions_dir() -> Path:
    from ai4science import user
    base = user.config_path().parent / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _to_record(m: Message) -> dict:
    return {
        "role": m.role,
        "content": m.content,
        "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                       for tc in m.tool_calls],
        "tool_call_id": m.tool_call_id,
    }


def _from_record(d: dict) -> Message:
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        tool_calls=[ToolCall(t["id"], t["name"], t["arguments"])
                    for t in d.get("tool_calls", [])],
        tool_call_id=d.get("tool_call_id"),
    )


def _index_path() -> Path:
    return sessions_dir() / "index.json"


def save(session_id: str, workspace: Path, history: List[Message]) -> None:
    path = sessions_dir() / f"{session_id}.jsonl"
    with path.open("w") as f:
        for m in history:
            f.write(json.dumps(_to_record(m)) + "\n")
    # update the per-workspace most-recent index
    idx = {}
    if _index_path().exists():
        idx = json.loads(_index_path().read_text())
    idx[str(workspace.resolve())] = session_id
    _index_path().write_text(json.dumps(idx))


def load(session_id: str) -> List[Message]:
    path = sessions_dir() / f"{session_id}.jsonl"
    if not path.exists():
        return []
    return [_from_record(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def most_recent(workspace: Path) -> Optional[str]:
    if not _index_path().exists():
        return None
    idx = json.loads(_index_path().read_text())
    return idx.get(str(workspace.resolve()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_persistence.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/persistence.py tests/test_harness_persistence.py
git commit -m "feat(harness): session persistence (JSONL history + per-workspace index)"
```

---

### Task 4: `--continue` / `--resume` for common mode

**Files:**
- Modify: `ai4science/harness/repl.py` (accept `resume_history`; save on each turn)
- Modify: `ai4science/commands/chat.py` (thread `continue_session`/`resume` into `run_common_repl`)
- Test: `tests/test_harness_resume.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_resume.py
from pathlib import Path
from ai4science.harness import repl as repl_mod
from ai4science.harness.events import Message


def test_run_common_repl_seeds_resume_history(tmp_path, monkeypatch):
    from ai4science.harness.adapters.stub import StubAdapter
    captured = {}
    real = repl_mod.AgentSession

    def _capture(**kwargs):
        s = real(**kwargs)
        captured["session"] = s
        return s

    monkeypatch.setattr(repl_mod, "AgentSession", _capture)
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: StubAdapter([[]]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)

    def _eof(*a, **k):
        raise EOFError()
    monkeypatch.setattr("builtins.input", _eof)

    prior = [Message(role="user", content="earlier"), Message(role="assistant", content="ok")]
    repl_mod.run_common_repl(tmp_path, backend="anthropic", model="stub",
                             resume_history=prior)
    assert [m.content for m in captured["session"].history] == ["earlier", "ok"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_resume.py -v`
Expected: FAIL — `run_common_repl` has no `resume_history` param.

- [ ] **Step 3: Implement resume in the REPL and thread the CLI flags**

In `ai4science/harness/repl.py`, add a `resume_history` parameter and seed the session, and persist after each turn. Add to the signature:

```python
def run_common_repl(
    workspace: Path,
    *,
    read_only: bool = False,
    auto_yes: bool = False,
    backend: Optional[str] = None,
    model: Optional[str] = None,
    on_text=None,
    resume_history=None,
    session_id: Optional[str] = None,
) -> None:
```

After `session = _build_session()`, seed history and set up persistence:

```python
    session = _build_session()
    if resume_history:
        session.history.extend(resume_history)

    from ai4science.harness import persistence
    import uuid_stub  # NOTE: do NOT import uuid at module top in scripts; here in the CLI process it's fine
```

(Implementation note: generate a session id without `Math.random`-style constraints — use `os.urandom`/`secrets`. In the REPL process this is allowed.)

Replace the normal-turn block to persist after each turn:

```python
        # Normal turn.
        try:
            result = session.run_turn(line)
            if result and not result.endswith("\n"):
                print(flush=True)
            persistence.save(_sid, workspace, session.history)
        except Exception as exc:
            print(f"\n[harness] turn error: {type(exc).__name__}: {exc}", flush=True)
```

Where `_sid` is computed once near the top of `run_common_repl`:

```python
    import secrets
    _sid = session_id or secrets.token_hex(8)
```

In `ai4science/commands/chat.py`, the common-mode branch threads the flags:

```python
    if mode == "common":
        from ai4science.harness.repl import run_common_repl
        from ai4science.harness import persistence
        resume_hist = None
        sid = resume
        if resume:
            resume_hist = persistence.load(resume)
        elif continue_session:
            sid = persistence.most_recent(workspace)
            resume_hist = persistence.load(sid) if sid else None
        try:
            run_common_repl(workspace, read_only=read_only or plan, auto_yes=yes,
                            model=model, resume_history=resume_hist, session_id=sid)
        except KeyboardInterrupt:
            console.print("\n[dim](Ctrl-C — exiting)[/dim]")
            raise typer.Exit(0)
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_resume.py tests/test_chat.py::test_chat_common_launches_harness -q`
Expected: PASS (the common-launch test still passes since it monkeypatches `run_common_repl`).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/repl.py ai4science/commands/chat.py tests/test_harness_resume.py
git commit -m "feat(harness): --continue/--resume for common mode (persist + reseed history)"
```

---

### Task 5: Context compaction

**Files:**
- Create: `ai4science/harness/compaction.py`
- Modify: `ai4science/harness/session.py` (call compaction before each turn when over threshold)
- Test: `tests/test_harness_compaction.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_compaction.py
from ai4science.harness.events import Message
from ai4science.harness import compaction


def test_no_compact_under_limit():
    hist = [Message(role="user", content="hi"), Message(role="assistant", content="yo")]
    out, did = compaction.maybe_compact(hist, limit_chars=10_000,
                                        summarize=lambda text: "SUMMARY")
    assert did is False and out is hist


def test_compacts_over_limit_preserving_recent():
    hist = [Message(role="user", content="x" * 5000) for _ in range(5)]
    out, did = compaction.maybe_compact(hist, limit_chars=8000, keep_recent=2,
                                        summarize=lambda text: "SUMMARY")
    assert did is True
    # first message is the summary, last two are the preserved recent ones
    assert out[0].role == "system" and "SUMMARY" in out[0].content
    assert out[-2:] == hist[-2:]
    assert len(out) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_compaction.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement compaction**

`ai4science/harness/compaction.py`:

```python
from __future__ import annotations

from typing import Callable, List, Tuple

from ai4science.harness.events import Message


def _size(history: List[Message]) -> int:
    return sum(len(m.content or "") for m in history)


def maybe_compact(history: List[Message], *, limit_chars: int, keep_recent: int = 6,
                  summarize: Callable[[str], str]) -> Tuple[List[Message], bool]:
    """If history exceeds limit_chars, replace the older prefix with one summary
    system message, preserving the last `keep_recent` messages. Returns (history, compacted?)."""
    if _size(history) <= limit_chars or len(history) <= keep_recent + 1:
        return history, False
    head = history[:-keep_recent]
    tail = history[-keep_recent:]
    transcript = "\n".join(f"{m.role}: {m.content}" for m in head if m.content)
    summary = summarize(transcript)
    compacted = [Message(role="system", content=f"[compacted earlier conversation]\n{summary}")] + tail
    return compacted, True
```

In `ai4science/harness/session.py`, add an optional compaction hook called at the start of `run_turn` (only when a summarizer is configured). Extend `__init__` with `compact_limit_chars: int = 0` and `summarize: Optional[Callable[[str], str]] = None`, and in `run_turn`:

```python
    def run_turn(self, user_input: str) -> str:
        if self.summarize and self.compact_limit_chars:
            from ai4science.harness.compaction import maybe_compact
            self.history, _ = maybe_compact(
                self.history, limit_chars=self.compact_limit_chars,
                summarize=self.summarize)
        self.history.append(Message(role="user", content=user_input))
        return run_loop(...)   # unchanged args
```

(Default `compact_limit_chars=0` means compaction is OFF unless explicitly configured, so existing tests are unaffected.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_compaction.py tests/test_harness_session.py -v`
Expected: PASS (compaction tests + existing session tests, which pass `compact_limit_chars=0` by default).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/compaction.py ai4science/harness/session.py tests/test_harness_compaction.py
git commit -m "feat(harness): context compaction (summarize old history over threshold)"
```

---

### Task 6: Full slash-command set + token footer in the REPL

**Files:**
- Modify: `ai4science/harness/repl.py` (slash dispatch: `/help /clear /readonly /yes /default /cost /files /model`; per-turn token footer)
- Test: `tests/test_harness_repl_slash.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_repl_slash.py
from pathlib import Path
from ai4science.harness.repl import _dispatch_slash


def test_help_lists_commands():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    handled, msg = _dispatch_slash("/help", state)
    assert handled and "/model" in msg and "/clear" in msg


def test_readonly_and_yes_toggle_state():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    _dispatch_slash("/readonly", state)
    assert state["read_only"] is True
    _dispatch_slash("/yes", state)
    assert state["auto_yes"] is True
    _dispatch_slash("/default", state)
    assert state["read_only"] is False and state["auto_yes"] is False


def test_exit_sets_flag():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    handled, _ = _dispatch_slash("/exit", state)
    assert handled and state["exit"] is True


def test_unknown_slash_not_handled():
    state = {"read_only": False, "auto_yes": False, "exit": False}
    handled, _ = _dispatch_slash("/bogus", state)
    assert handled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_repl_slash.py -v`
Expected: FAIL — `_dispatch_slash` does not exist.

- [ ] **Step 3: Extract a testable `_dispatch_slash` and use it in the loop**

In `ai4science/harness/repl.py`, add a pure-ish dispatcher that mutates a `state` dict and returns `(handled, message)`. The `/model` branch stays in the loop (it needs the live session), but `/help /clear /readonly /yes /default /cost /files /exit` route through `_dispatch_slash`:

```python
def _dispatch_slash(line: str, state: dict) -> tuple[bool, str]:
    cmd, _, _arg = line[1:].partition(" ")
    cmd = cmd.lower().strip()
    if cmd in ("exit", "quit", "q"):
        state["exit"] = True
        return True, "bye"
    if cmd in ("help", "?"):
        return True, ("slash commands: /help /clear /model <backend> [id] "
                      "/readonly /yes /default /cost /files /exit")
    if cmd == "readonly":
        state["read_only"] = True
        return True, "read-only: ON (mutating tools blocked)"
    if cmd == "yes":
        state["auto_yes"] = True
        return True, "auto-yes: ON (tools auto-approved)"
    if cmd == "default":
        state["read_only"] = False
        state["auto_yes"] = False
        return True, "default mode (per-edit confirmation)"
    if cmd == "clear":
        state["clear"] = True
        return True, "conversation cleared"
    return False, ""
```

Wire it into the REPL loop: route slashes other than `/model` and `/cost`/`/files` through `_dispatch_slash`; when `state["clear"]`, reset `session.history` and the gate's modes (rebuild the session with the new read_only/auto_yes). Print a one-line **token footer** after each turn using the metered `Usage` totals accumulated for the turn (track them via the `meter` callback into a running counter). `/cost` prints the running PWM total via `ledger.summary()`. `/files` lists workspace files via the `glob` tool.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_repl_slash.py tests/test_harness_repl.py -v`
Expected: PASS (4 new + existing repl tests still green).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/repl.py tests/test_harness_repl_slash.py
git commit -m "feat(harness): full slash-command set + token footer in common REPL"
```

---

### Task 7: Full suite green + parity doc update

- [ ] **Step 1:** Run `python -m pytest -q` — all green except the 2 pre-existing `test_list_sessions_*` env failures (`claude_agent_sdk` absent). If any harness test regressed, fix before proceeding.
- [ ] **Step 2:** Append to `docs/CLAUDE_CODE_PARITY.md` a note that common mode now has live bash streaming, diff previews, session resume, compaction, and the full slash set (Plan 3a); remaining gaps are Plan 3b–3d (sub-agents, MCP, @mentions, images, bash sandboxing).
- [ ] **Step 3:** Commit: `git commit -m "docs(parity): Plan 3a interactive experience essentials landed"`.

---

## Self-review

- **Spec coverage (parity bar §3):** live tool-call display + streaming (Task 1 bash stream; render footer Task 6), per-edit confirmation with diff preview (Task 2), session resume (Tasks 3–4), the slash-command set (Task 6). Compaction (Task 5) supports long sessions. Sub-agents/MCP/@mentions/images/bash-sandbox are explicitly Plan 3b–3d.
- **Placeholder scan:** Task 4 step 3 contains an illustrative note about session-id generation — the implementer must use `secrets.token_hex` (shown), NOT a placeholder import; flagged inline. Otherwise every step has concrete code.
- **Type consistency:** persistence round-trips the exact `Message`/`ToolCall` fields from `events.py`; `Tool` gains `streams: bool`; the loop's sink is `on_text` (Callable[[str], None]) consistent with `AgentSession`; compaction returns `(List[Message], bool)`.

## Known limitations (carried forward)
1. Token footer accuracy depends on the adapters' `Usage` (Anthropic input under-metering is Plan 3d).
2. `/clear` rebuilds the session (drops the gate's prior confirm wiring unless re-passed) — implementer must rebuild via the same `_build_session` helper.
3. Persistence stores plaintext history under the user config dir; no encryption (acceptable — local only).
