# Native Interactive Harness — Claude-Code Experience Across Brands (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one native streaming agentic harness so interactive common mode feels exactly like Claude Code — live token streaming, per-edit confirmation, slash commands — with the LLM brand (Anthropic / ChatGPT / Gemini) as a swappable adapter behind an identical UX.

**Architecture:** A new `ai4science/harness/` package: normalized message/event types; a `Tool` registry with core tools (read/write/edit/bash/grep/glob); a `PermissionGate` (read-only / auto-yes / prompt + sandbox guard); an `AgentAdapter` interface with Anthropic/OpenAI/Gemini streaming-function-calling adapters (reusing `llm/execute`'s credential setup) plus a `StubAdapter` for CI; an `AgentSession` + agent `loop` that drives the adapter, dispatches tools through the gate, streams output, and meters usage to the PWM ledger. `commands/chat.py` drives `AgentSession` for all brands; `/model` switches brand with zero UX change.

**Tech Stack:** Python 3, Typer (CLI), pytest + monkeypatch, provider SDKs/HTTP (anthropic, openai, google-genai / Vertex), existing `ai4science.llm` (routing/execute/pricing/ledger) and `ai4science.user`.

**Spec:** `docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md` (§3 parity bar, §5 harness architecture).

---

## Design decisions carried from the spec

- All brands (incl. Anthropic) route through the native harness for a **uniform** experience; `claude-agent-sdk` is retained only as optional fallback, not the interactive path.
- Adapters expose a **pure, testable** translate/parse core; the streaming HTTP/SDK call is a thin wrapper around it. CI tests the translate/parse over canned streams — **no real LLM calls in CI**.
- History is **brand-neutral** (a normalized `Message` list); switching brand mid-session re-renders the same history through a different adapter.
- The **PermissionGate** also enforces the PWM sandbox: tools may not touch `judge/`, `hidden_tests/`, locked benchmark files, or paths outside the workspace.

## File structure (created in this plan)

| File | Responsibility |
|---|---|
| `ai4science/harness/__init__.py` | package marker |
| `ai4science/harness/events.py` | `Message`, `ToolSpec`, and stream `Event` types |
| `ai4science/harness/tools/base.py` | `Tool` dataclass + `Registry` |
| `ai4science/harness/tools/fs.py` | read / write / edit / grep / glob tools |
| `ai4science/harness/tools/shell.py` | bash tool |
| `ai4science/harness/tools/__init__.py` | assemble the default registry |
| `ai4science/harness/permissions.py` | `PermissionGate` + sandbox path guard |
| `ai4science/harness/adapters/base.py` | `AgentAdapter` ABC |
| `ai4science/harness/adapters/stub.py` | `StubAdapter` (scripted events, for tests) |
| `ai4science/harness/adapters/anthropic.py` | Anthropic streaming + tool-calling adapter |
| `ai4science/harness/adapters/openai.py` | OpenAI streaming + tool-calling adapter |
| `ai4science/harness/adapters/gemini.py` | Gemini streaming + tool-calling adapter |
| `ai4science/harness/loop.py` | agent loop (drive adapter, dispatch tools, meter) |
| `ai4science/harness/session.py` | `AgentSession` (history, brand, modes, `run_turn`) |
| `tests/test_harness_*.py` | one test file per module |

Modified: `ai4science/commands/chat.py` (drive `AgentSession`; `/model` brand switch).

---

### Task 1: Normalized message & event types

**Files:**
- Create: `ai4science/harness/__init__.py`, `ai4science/harness/events.py`
- Test: `tests/test_harness_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_events.py
from ai4science.harness.events import (
    Message, ToolSpec, TextDelta, ToolCall, Usage, Done,
)


def test_message_roundtrip():
    m = Message(role="user", content="hello")
    assert m.role == "user" and m.content == "hello"
    assert m.tool_calls == [] and m.tool_call_id is None


def test_tool_spec_fields():
    t = ToolSpec(name="read", description="read a file",
                 parameters={"type": "object", "properties": {"path": {"type": "string"}}})
    assert t.name == "read"
    assert t.parameters["properties"]["path"]["type"] == "string"


def test_event_variants():
    assert TextDelta(text="hi").text == "hi"
    tc = ToolCall(id="c1", name="bash", arguments={"cmd": "ls"})
    assert tc.name == "bash" and tc.arguments["cmd"] == "ls"
    assert Usage(input=10, output=5, total=15).total == 15
    assert isinstance(Done(), Done)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/spiritai/pwm/Physics_World_Model/AI4Science && python -m pytest tests/test_harness_events.py -v`
Expected: FAIL — `ModuleNotFoundError: ai4science.harness`

- [ ] **Step 3: Implement events**

```python
# ai4science/harness/__init__.py
"""Native streaming agentic harness — brand-agnostic Claude-Code experience."""
```

```python
# ai4science/harness/events.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]   # JSON Schema object


@dataclass
class Message:
    role: str                                  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: List["ToolCall"] = field(default_factory=list)  # assistant tool requests
    tool_call_id: Optional[str] = None         # set on role="tool" result messages


# ---- stream events (adapter -> loop) ----
@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Usage:
    input: Optional[int]
    output: Optional[int]
    total: Optional[int]


@dataclass
class Done:
    stop_reason: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_events.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/__init__.py ai4science/harness/events.py tests/test_harness_events.py
git commit -m "feat(harness): normalized message + stream event types"
```

---

### Task 2: Tool base + registry + filesystem tools

**Files:**
- Create: `ai4science/harness/tools/base.py`, `ai4science/harness/tools/fs.py`
- Test: `tests/test_harness_tools_fs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_tools_fs.py
from pathlib import Path
from ai4science.harness.tools.base import Tool
from ai4science.harness.tools import fs


def test_read_tool(tmp_path):
    (tmp_path / "a.txt").write_text("line1\nline2\n")
    out = fs.read(tmp_path, path="a.txt")
    assert "line1" in out and "line2" in out


def test_write_then_read(tmp_path):
    fs.write(tmp_path, path="b.txt", content="hello")
    assert (tmp_path / "b.txt").read_text() == "hello"


def test_edit_replaces_unique_string(tmp_path):
    (tmp_path / "c.py").write_text("x = 1\ny = 2\n")
    fs.edit(tmp_path, path="c.py", old="x = 1", new="x = 42")
    assert (tmp_path / "c.py").read_text() == "x = 42\ny = 2\n"


def test_edit_errors_when_not_unique(tmp_path):
    (tmp_path / "d.py").write_text("a\na\n")
    try:
        fs.edit(tmp_path, path="d.py", old="a", new="b")
        assert False, "should have raised"
    except ValueError as e:
        assert "unique" in str(e).lower()


def test_glob_and_grep(tmp_path):
    (tmp_path / "x.py").write_text("import os\n")
    (tmp_path / "y.txt").write_text("nope\n")
    assert "x.py" in fs.glob(tmp_path, pattern="*.py")
    assert "x.py" in fs.grep(tmp_path, pattern="import os")


def test_tool_dataclass_is_callable():
    t = Tool(name="read", description="d",
             parameters={"type": "object"}, func=fs.read, mutating=False)
    assert t.name == "read" and t.mutating is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_tools_fs.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement tool base + fs tools**

```python
# ai4science/harness/tools/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]     # JSON Schema
    func: Callable[..., str]       # func(workspace: Path, **args) -> str
    mutating: bool = False         # True => must pass the permission gate


class Registry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def names(self):
        return list(self._tools.keys())

    def specs(self):
        from ai4science.harness.events import ToolSpec
        return [ToolSpec(t.name, t.description, t.parameters) for t in self._tools.values()]
```

```python
# ai4science/harness/tools/fs.py
from __future__ import annotations

import fnmatch
import os
from pathlib import Path


def read(workspace: Path, *, path: str) -> str:
    p = (workspace / path)
    text = p.read_text()
    lines = text.splitlines()
    return "\n".join(f"{i+1}\t{ln}" for i, ln in enumerate(lines))


def write(workspace: Path, *, path: str, content: str) -> str:
    p = (workspace / path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} bytes to {path}"


def edit(workspace: Path, *, path: str, old: str, new: str) -> str:
    p = (workspace / path)
    text = p.read_text()
    count = text.count(old)
    if count == 0:
        raise ValueError(f"old string not found in {path}")
    if count > 1:
        raise ValueError(f"old string is not unique in {path} ({count} matches)")
    p.write_text(text.replace(old, new, 1))
    return f"edited {path}"


def glob(workspace: Path, *, pattern: str) -> str:
    hits = []
    for root, _dirs, files in os.walk(workspace):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), workspace)
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(f, pattern):
                hits.append(rel)
    return "\n".join(sorted(hits))


def grep(workspace: Path, *, pattern: str) -> str:
    import re
    rx = re.compile(pattern)
    out = []
    for root, _dirs, files in os.walk(workspace):
        for f in files:
            fp = Path(root) / f
            try:
                for i, ln in enumerate(fp.read_text().splitlines()):
                    if rx.search(ln):
                        out.append(f"{os.path.relpath(fp, workspace)}:{i+1}:{ln}")
            except (UnicodeDecodeError, OSError):
                continue
    return "\n".join(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_tools_fs.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/tools/base.py ai4science/harness/tools/fs.py tests/test_harness_tools_fs.py
git commit -m "feat(harness): tool registry + filesystem tools"
```

---

### Task 3: Shell tool + default registry assembly

**Files:**
- Create: `ai4science/harness/tools/shell.py`, `ai4science/harness/tools/__init__.py`
- Test: `tests/test_harness_tools_shell.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_tools_shell.py
from ai4science.harness.tools import shell, default_registry


def test_bash_runs_and_captures(tmp_path):
    (tmp_path / "f.txt").write_text("hi")
    out = shell.bash(tmp_path, cmd="cat f.txt")
    assert "hi" in out


def test_bash_reports_nonzero(tmp_path):
    out = shell.bash(tmp_path, cmd="exit 3")
    assert "exit code 3" in out.lower()


def test_default_registry_has_core_tools():
    reg = default_registry()
    assert set(["read", "write", "edit", "bash", "grep", "glob"]).issubset(set(reg.names()))
    # mutating flags correct
    assert reg.get("read").mutating is False
    assert reg.get("write").mutating is True
    assert reg.get("edit").mutating is True
    assert reg.get("bash").mutating is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_tools_shell.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement shell tool + registry**

```python
# ai4science/harness/tools/shell.py
from __future__ import annotations

import subprocess
from pathlib import Path

BASH_TIMEOUT_SECONDS = 300


def bash(workspace: Path, *, cmd: str) -> str:
    try:
        p = subprocess.run(cmd, shell=True, cwd=str(workspace),
                           capture_output=True, text=True, timeout=BASH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return f"(timed out after {BASH_TIMEOUT_SECONDS}s)"
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        out += f"\n(exit code {p.returncode})"
    return out
```

```python
# ai4science/harness/tools/__init__.py
from __future__ import annotations

from ai4science.harness.tools.base import Registry, Tool
from ai4science.harness.tools import fs, shell

_STR = {"type": "string"}


def default_registry() -> Registry:
    reg = Registry()
    reg.add(Tool("read", "Read a file (returns numbered lines).",
                 {"type": "object", "properties": {"path": _STR}, "required": ["path"]},
                 fs.read, mutating=False))
    reg.add(Tool("write", "Write (overwrite) a file.",
                 {"type": "object", "properties": {"path": _STR, "content": _STR},
                  "required": ["path", "content"]}, fs.write, mutating=True))
    reg.add(Tool("edit", "Replace a unique old string with new in a file.",
                 {"type": "object", "properties": {"path": _STR, "old": _STR, "new": _STR},
                  "required": ["path", "old", "new"]}, fs.edit, mutating=True))
    reg.add(Tool("bash", "Run a shell command in the workspace.",
                 {"type": "object", "properties": {"cmd": _STR}, "required": ["cmd"]},
                 shell.bash, mutating=True))
    reg.add(Tool("grep", "Regex search across files.",
                 {"type": "object", "properties": {"pattern": _STR}, "required": ["pattern"]},
                 fs.grep, mutating=False))
    reg.add(Tool("glob", "Glob for files by pattern.",
                 {"type": "object", "properties": {"pattern": _STR}, "required": ["pattern"]},
                 fs.glob, mutating=False))
    return reg


__all__ = ["Registry", "Tool", "default_registry", "fs", "shell"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_tools_shell.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/tools/shell.py ai4science/harness/tools/__init__.py tests/test_harness_tools_shell.py
git commit -m "feat(harness): bash tool + default tool registry"
```

---

### Task 4: Permission gate + sandbox guard

**Files:**
- Create: `ai4science/harness/permissions.py`
- Test: `tests/test_harness_permissions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_permissions.py
from pathlib import Path
from ai4science.harness.permissions import PermissionGate, SandboxError


def test_read_only_blocks_mutating(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    ok, reason = gate.allow("edit", {"path": "a.py", "old": "x", "new": "y"})
    assert ok is False and "read-only" in reason.lower()


def test_read_only_allows_read(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    ok, _ = gate.allow("read", {"path": "a.py"})
    assert ok is True


def test_auto_yes_allows_mutating(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    ok, _ = gate.allow("write", {"path": "a.py", "content": "x"})
    assert ok is True


def test_prompt_uses_confirm_callback(tmp_path):
    answers = iter([True, False])
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=False,
                          confirm=lambda name, args, preview: next(answers))
    ok1, _ = gate.allow("write", {"path": "a.py", "content": "x"})
    ok2, _ = gate.allow("bash", {"cmd": "rm -rf /"})
    assert ok1 is True and ok2 is False


def test_sandbox_blocks_protected_paths(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    for bad in ["judge/x.py", "hidden_tests/t.py", "../escape.py"]:
        ok, reason = gate.allow("write", {"path": bad, "content": "x"})
        assert ok is False and "sandbox" in reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_permissions.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the permission gate**

```python
# ai4science/harness/permissions.py
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

PROTECTED_DIRS = ("judge", "hidden_tests")


class SandboxError(Exception):
    pass


class PermissionGate:
    """Decides whether a tool call may run. Mirrors Claude Code's modes."""

    def __init__(self, *, workspace: Path, read_only: bool, auto_yes: bool,
                 confirm: Optional[Callable[[str, Dict, str], bool]] = None) -> None:
        self.workspace = workspace.resolve()
        self.read_only = read_only
        self.auto_yes = auto_yes
        self.confirm = confirm
        self._mutating = {"write", "edit", "bash"}

    def _sandbox_ok(self, name: str, args: Dict) -> Tuple[bool, str]:
        path = args.get("path")
        if path:
            target = (self.workspace / path).resolve()
            try:
                target.relative_to(self.workspace)
            except ValueError:
                return False, "sandbox: path escapes the workspace"
            parts = Path(path).parts
            if parts and parts[0] in PROTECTED_DIRS:
                return False, f"sandbox: '{parts[0]}/' is protected"
        return True, ""

    def allow(self, name: str, args: Dict) -> Tuple[bool, str]:
        sok, sreason = self._sandbox_ok(name, args)
        if not sok:
            return False, sreason
        if name not in self._mutating:
            return True, ""
        if self.read_only:
            return False, "read-only mode: mutating tools are blocked"
        if self.auto_yes:
            return True, ""
        if self.confirm is None:
            return False, "no confirmation handler available"
        preview = _preview(name, args)
        return bool(self.confirm(name, args, preview)), "user decision"


def _preview(name: str, args: Dict) -> str:
    if name == "bash":
        return f"$ {args.get('cmd', '')}"
    if name == "write":
        return f"write {args.get('path')} ({len(args.get('content', ''))} bytes)"
    if name == "edit":
        return f"edit {args.get('path')}: {args.get('old')!r} -> {args.get('new')!r}"
    return f"{name} {args}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_permissions.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/permissions.py tests/test_harness_permissions.py
git commit -m "feat(harness): permission gate + PWM sandbox guard"
```

---

### Task 5: Adapter interface + StubAdapter

**Files:**
- Create: `ai4science/harness/adapters/__init__.py`, `ai4science/harness/adapters/base.py`, `ai4science/harness/adapters/stub.py`
- Test: `tests/test_harness_stub_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_stub_adapter.py
from ai4science.harness.events import Message, TextDelta, ToolCall, Usage, Done
from ai4science.harness.adapters.stub import StubAdapter


def test_stub_emits_scripted_events():
    script = [
        [TextDelta("Let me read it. "), ToolCall("c1", "read", {"path": "a.py"}), Usage(5, 2, 7), Done("tool_use")],
        [TextDelta("All done."), Usage(3, 1, 4), Done("end")],
    ]
    a = StubAdapter(script=script)
    msgs = [Message(role="user", content="hi")]
    ev1 = list(a.stream(msgs, tools=[], model="stub", reasoning="low"))
    assert any(isinstance(e, ToolCall) for e in ev1)
    ev2 = list(a.stream(msgs, tools=[], model="stub", reasoning="low"))
    assert isinstance(ev2[-1], Done)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_stub_adapter.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement adapter base + stub**

```python
# ai4science/harness/adapters/__init__.py
"""Provider adapters: translate normalized messages+tools to each brand's stream."""
```

```python
# ai4science/harness/adapters/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, List

from ai4science.harness.events import Message, ToolSpec


class AgentAdapter(ABC):
    backend: str = "base"

    @abstractmethod
    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        """Yield TextDelta / ToolCall / Usage / Done events for one turn."""
        raise NotImplementedError
```

```python
# ai4science/harness/adapters/stub.py
from __future__ import annotations

from typing import Iterator, List

from ai4science.harness.adapters.base import AgentAdapter
from ai4science.harness.events import Message, ToolSpec


class StubAdapter(AgentAdapter):
    backend = "stub"

    def __init__(self, script: List[List[object]]) -> None:
        self._script = list(script)
        self._i = 0

    def stream(self, messages: List[Message], tools: List[ToolSpec], *,
               model: str, reasoning: str) -> Iterator[object]:
        turn = self._script[min(self._i, len(self._script) - 1)]
        self._i += 1
        for ev in turn:
            yield ev
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_stub_adapter.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/__init__.py ai4science/harness/adapters/base.py ai4science/harness/adapters/stub.py tests/test_harness_stub_adapter.py
git commit -m "feat(harness): adapter interface + stub adapter"
```

---

### Task 6: Agent loop + session (end-to-end with stub)

**Files:**
- Create: `ai4science/harness/loop.py`, `ai4science/harness/session.py`
- Test: `tests/test_harness_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_session.py
from pathlib import Path
from ai4science.harness.events import Message, TextDelta, ToolCall, Usage, Done
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.session import AgentSession
from ai4science.harness.tools import default_registry


def test_session_runs_tool_then_finishes(tmp_path):
    (tmp_path / "a.py").write_text("print('x')\n")
    script = [
        # turn 1: model reads a file, then stops for tool result
        [TextDelta("reading "), ToolCall("c1", "read", {"path": "a.py"}), Usage(5, 2, 7), Done("tool_use")],
        # turn 2: model responds with final text
        [TextDelta("the file prints x."), Usage(3, 1, 4), Done("end")],
    ]
    metered = []
    sess = AgentSession(
        adapter=StubAdapter(script), model="stub", backend="anthropic",
        workspace=tmp_path, registry=default_registry(),
        read_only=False, auto_yes=True,
        on_text=lambda t: None,
        meter=lambda usage: metered.append(usage),
    )
    final = sess.run_turn("what does a.py do?")
    assert "prints x" in final
    # history grew: user, assistant(tool_call), tool result, assistant(final)
    roles = [m.role for m in sess.history]
    assert roles[0] == "user"
    assert any(m.role == "tool" for m in sess.history)
    assert sess.history[-1].role == "assistant"
    assert len(metered) == 2     # two adapter turns metered


def test_session_respects_read_only(tmp_path):
    script = [
        [ToolCall("c1", "write", {"path": "new.py", "content": "x"}), Done("tool_use")],
        [TextDelta("could not write."), Done("end")],
    ]
    sess = AgentSession(
        adapter=StubAdapter(script), model="stub", backend="anthropic",
        workspace=tmp_path, registry=default_registry(),
        read_only=True, auto_yes=False, on_text=lambda t: None, meter=lambda u: None,
    )
    sess.run_turn("create new.py")
    assert not (tmp_path / "new.py").exists()
    # the tool result message should record the block reason
    tool_msgs = [m for m in sess.history if m.role == "tool"]
    assert tool_msgs and "read-only" in tool_msgs[0].content.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_session.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement loop + session**

```python
# ai4science/harness/loop.py
from __future__ import annotations

from pathlib import Path
from typing import Callable, List

from ai4science.harness.events import Message, TextDelta, ToolCall, Usage, Done
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools.base import Registry

MAX_TOOL_ITERATIONS = 50


def run_loop(*, adapter, model: str, reasoning: str, history: List[Message],
             workspace: Path, registry: Registry, gate: PermissionGate,
             on_text: Callable[[str], None], meter: Callable[[Usage], None]) -> str:
    """Drive one user turn to completion (text + any tool calls). Returns final text."""
    final_text_parts: List[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        text_buf: List[str] = []
        calls: List[ToolCall] = []
        for ev in adapter.stream(history, registry.specs(), model=model, reasoning=reasoning):
            if isinstance(ev, TextDelta):
                text_buf.append(ev.text)
                on_text(ev.text)
            elif isinstance(ev, ToolCall):
                calls.append(ev)
            elif isinstance(ev, Usage):
                meter(ev)
            elif isinstance(ev, Done):
                pass

        assistant_text = "".join(text_buf)
        history.append(Message(role="assistant", content=assistant_text, tool_calls=list(calls)))
        if assistant_text:
            final_text_parts.append(assistant_text)

        if not calls:
            break

        for tc in calls:
            ok, reason = gate.allow(tc.name, tc.arguments)
            if not ok:
                result = f"[blocked] {reason}"
            else:
                try:
                    tool = registry.get(tc.name)
                    result = tool.func(workspace, **tc.arguments)
                except Exception as exc:
                    result = f"[error] {exc}"
            history.append(Message(role="tool", content=str(result), tool_call_id=tc.id))

    return "".join(final_text_parts)
```

```python
# ai4science/harness/session.py
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from ai4science.harness.events import Message, Usage
from ai4science.harness.loop import run_loop
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools import default_registry
from ai4science.harness.tools.base import Registry


class AgentSession:
    """A live, brand-swappable conversation. History is brand-neutral."""

    def __init__(self, *, adapter, model: str, backend: str, workspace: Path,
                 registry: Optional[Registry] = None,
                 read_only: bool = False, auto_yes: bool = False,
                 reasoning: str = "high",
                 confirm: Optional[Callable[[str, dict, str], bool]] = None,
                 on_text: Callable[[str], None] = lambda t: None,
                 meter: Callable[[Usage], None] = lambda u: None) -> None:
        self.adapter = adapter
        self.model = model
        self.backend = backend
        self.workspace = workspace
        self.registry = registry or default_registry()
        self.reasoning = reasoning
        self.on_text = on_text
        self.meter = meter
        self.history: List[Message] = []
        self.gate = PermissionGate(workspace=workspace, read_only=read_only,
                                   auto_yes=auto_yes, confirm=confirm)

    def set_brand(self, adapter, model: str, backend: str) -> None:
        """Swap the brand mid-session; history is preserved (brand-neutral)."""
        self.adapter, self.model, self.backend = adapter, model, backend

    def run_turn(self, user_input: str) -> str:
        self.history.append(Message(role="user", content=user_input))
        return run_loop(
            adapter=self.adapter, model=self.model, reasoning=self.reasoning,
            history=self.history, workspace=self.workspace, registry=self.registry,
            gate=self.gate, on_text=self.on_text, meter=self.meter,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_session.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/loop.py ai4science/harness/session.py tests/test_harness_session.py
git commit -m "feat(harness): agent loop + brand-swappable session"
```

---

### Task 7: Anthropic streaming adapter

**Files:**
- Create: `ai4science/harness/adapters/anthropic.py`
- Test: `tests/test_harness_adapter_anthropic.py`

The adapter has a **pure** translate/parse core (CI-tested) and a thin streaming call
(manual E2E). Reuse client/credential setup from `ai4science/llm/execute._run_anthropic`.

- [ ] **Step 1: Write the failing test (translate + parse, no network)**

```python
# tests/test_harness_adapter_anthropic.py
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Usage, Done
from ai4science.harness.adapters.anthropic import AnthropicAdapter


def test_translate_tools_to_anthropic_schema():
    a = AnthropicAdapter()
    specs = [ToolSpec("read", "read a file", {"type": "object", "properties": {"path": {"type": "string"}}})]
    out = a._translate_tools(specs)
    assert out[0]["name"] == "read"
    assert out[0]["input_schema"]["properties"]["path"]["type"] == "string"


def test_translate_messages_roles():
    a = AnthropicAdapter()
    msgs = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="reading", tool_calls=[ToolCall("c1", "read", {"path": "a"})]),
        Message(role="tool", content="contents", tool_call_id="c1"),
    ]
    out = a._translate_messages(msgs)
    assert out[0]["role"] == "user"
    # assistant tool call becomes a tool_use block; tool result becomes a user tool_result block
    assert any(b.get("type") == "tool_use" for b in out[1]["content"])
    assert out[2]["role"] == "user"
    assert any(b.get("type") == "tool_result" for b in out[2]["content"])


def test_parse_stream_events():
    # simulate the anthropic streaming event objects via lightweight stand-ins
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    raw = [
        _E(type="content_block_delta", delta=_E(type="text_delta", text="Hello")),
        _E(type="content_block_start", content_block=_E(type="tool_use", id="c1", name="read", input={})),
        _E(type="content_block_delta", delta=_E(type="input_json_delta", partial_json='{"path": "a.py"}')),
        _E(type="content_block_stop"),
        _E(type="message_delta", usage=_E(output_tokens=5), delta=_E(stop_reason="tool_use")),
        _E(type="message_stop"),
    ]
    a = AnthropicAdapter()
    events = list(a._parse_stream(raw, input_tokens=10))
    assert any(isinstance(e, TextDelta) and e.text == "Hello" for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert tcs and tcs[0].name == "read" and tcs[0].arguments == {"path": "a.py"}
    assert any(isinstance(e, Usage) for e in events)
    assert any(isinstance(e, Done) for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_adapter_anthropic.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the Anthropic adapter**

```python
# ai4science/harness/adapters/anthropic.py
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

    def _parse_stream(self, raw_events, input_tokens: int) -> Iterator[object]:
        cur_id = cur_name = None
        cur_json = ""
        for ev in raw_events:
            t = getattr(ev, "type", None)
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
        # input token count is read from the final message_delta in practice; pass 0 fallback.
        with client.messages.stream(**kwargs) as s:
            yield from self._parse_stream(s, input_tokens=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_adapter_anthropic.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/anthropic.py tests/test_harness_adapter_anthropic.py
git commit -m "feat(harness): Anthropic streaming + tool-calling adapter"
```

---

### Task 8: OpenAI streaming adapter

**Files:**
- Create: `ai4science/harness/adapters/openai.py`
- Test: `tests/test_harness_adapter_openai.py`

Mirror Task 7 for OpenAI Chat Completions function-calling (reuse credential setup from
`llm/execute._run_openai`). Tools translate to `{"type": "function", "function": {name, description, parameters}}`;
assistant tool calls map to `tool_calls`; tool results map to `{"role": "tool", "tool_call_id", "content"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_adapter_openai.py
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Done
from ai4science.harness.adapters.openai import OpenAIAdapter


def test_translate_tools_function_schema():
    a = OpenAIAdapter()
    out = a._translate_tools([ToolSpec("bash", "run", {"type": "object", "properties": {"cmd": {"type": "string"}}})])
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "bash"


def test_translate_messages_tool_result():
    a = OpenAIAdapter()
    msgs = [
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "bash", {"cmd": "ls"})]),
        Message(role="tool", content="a.py", tool_call_id="c1"),
    ]
    out = a._translate_messages(msgs)
    assert out[0]["tool_calls"][0]["id"] == "c1"
    assert out[1]["role"] == "tool" and out[1]["tool_call_id"] == "c1"


def test_parse_stream_collects_tool_call_deltas():
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    # OpenAI streams tool-call function args in fragments across choices[0].delta.tool_calls
    chunks = [
        _E(choices=[_E(delta=_E(content="ok ", tool_calls=None), finish_reason=None)], usage=None),
        _E(choices=[_E(delta=_E(content=None, tool_calls=[
            _E(index=0, id="c1", function=_E(name="bash", arguments='{"cmd":'))]), finish_reason=None)], usage=None),
        _E(choices=[_E(delta=_E(content=None, tool_calls=[
            _E(index=0, id=None, function=_E(name=None, arguments=' "ls"}'))]), finish_reason="tool_calls")], usage=None),
    ]
    a = OpenAIAdapter()
    events = list(a._parse_stream(chunks))
    assert any(isinstance(e, TextDelta) for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert tcs and tcs[0].name == "bash" and tcs[0].arguments == {"cmd": "ls"}
    assert any(isinstance(e, Done) for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_adapter_openai.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the OpenAI adapter**

```python
# ai4science/harness/adapters/openai.py
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
            if m.role in ("system", "user"):
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

    def _parse_stream(self, chunks) -> Iterator[object]:
        acc: dict = {}   # index -> {id, name, args}
        for ch in chunks:
            choice = ch.choices[0]
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
                    yield Usage(getattr(u, "prompt_tokens", None),
                                getattr(u, "completion_tokens", None),
                                getattr(u, "total_tokens", None))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_adapter_openai.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/openai.py tests/test_harness_adapter_openai.py
git commit -m "feat(harness): OpenAI streaming + tool-calling adapter"
```

---

### Task 9: Gemini streaming adapter

**Files:**
- Create: `ai4science/harness/adapters/gemini.py`
- Test: `tests/test_harness_adapter_gemini.py`

Mirror for Gemini (`google-genai`). Tools translate to function declarations; assistant
tool calls map to `functionCall` parts; tool results map to a `function` role with a
`functionResponse` part. Reuse credential setup from `llm/execute._run_gemini`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_adapter_gemini.py
from ai4science.harness.events import Message, ToolSpec, TextDelta, ToolCall, Done
from ai4science.harness.adapters.gemini import GeminiAdapter


def test_translate_tools_function_declarations():
    a = GeminiAdapter()
    out = a._translate_tools([ToolSpec("read", "r", {"type": "object", "properties": {"path": {"type": "string"}}})])
    # one tools entry with function_declarations list
    assert out[0]["function_declarations"][0]["name"] == "read"


def test_translate_messages_contents_roles():
    a = GeminiAdapter()
    msgs = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "read", {"path": "a"})]),
        Message(role="tool", content="data", tool_call_id="c1"),
    ]
    out = a._translate_messages(msgs)
    assert out[0]["role"] == "user"
    assert out[1]["role"] == "model"
    assert any("functionCall" in p for p in out[1]["parts"])
    assert out[2]["role"] == "function"


def test_parse_stream_text_and_function_call():
    class _E:
        def __init__(self, **k): self.__dict__.update(k)
    chunks = [
        _E(candidates=[_E(content=_E(parts=[_E(text="hi ", function_call=None)]))], usage_metadata=None),
        _E(candidates=[_E(content=_E(parts=[
            _E(text=None, function_call=_E(name="read", args={"path": "a.py"}))]))],
           usage_metadata=_E(prompt_token_count=4, candidates_token_count=3, total_token_count=7)),
    ]
    a = GeminiAdapter()
    events = list(a._parse_stream(chunks))
    assert any(isinstance(e, TextDelta) for e in events)
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert tcs and tcs[0].name == "read" and tcs[0].arguments == {"path": "a.py"}
    assert any(isinstance(e, Done) for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_adapter_gemini.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the Gemini adapter**

```python
# ai4science/harness/adapters/gemini.py
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
                        yield ToolCall(f"gem_{fc.name}", fc.name, dict(fc.args or {}))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_adapter_gemini.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/adapters/gemini.py tests/test_harness_adapter_gemini.py
git commit -m "feat(harness): Gemini streaming + tool-calling adapter"
```

---

### Task 10: Adapter factory + accounting + REPL wiring

**Files:**
- Create: `ai4science/harness/adapters/factory.py`
- Modify: `ai4science/commands/chat.py` (drive `AgentSession` for common mode; `/model` brand switch)
- Test: `tests/test_harness_factory.py`, plus a chat integration test

- [ ] **Step 1: Write the failing test (factory + metering helper)**

```python
# tests/test_harness_factory.py
from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.harness.adapters.anthropic import AnthropicAdapter
from ai4science.harness.events import Usage
from ai4science.llm import routing


def test_adapter_for_backend():
    assert isinstance(adapter_for("anthropic"), AnthropicAdapter)


def test_make_meter_records_to_ledger(monkeypatch):
    monkeypatch.setattr(routing, "_select_source",
                        lambda backend: ("wallet", "p1", "0xW", 1.0))
    recorded = []
    import ai4science.harness.adapters.factory as fac
    monkeypatch.setattr(fac.ledger, "record", lambda **kw: recorded.append(kw))
    meter = make_meter(backend="anthropic", model="claude-opus-4-8")
    meter(Usage(input=10, output=4, total=14))
    assert recorded and recorded[0]["model"] == "claude-opus-4-8"
    assert recorded[0]["wallet"] == "0xW"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_factory.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement factory + meter**

```python
# ai4science/harness/adapters/factory.py
from __future__ import annotations

from typing import Callable

from ai4science.harness.adapters.anthropic import AnthropicAdapter
from ai4science.harness.adapters.openai import OpenAIAdapter
from ai4science.harness.adapters.gemini import GeminiAdapter
from ai4science.harness.events import Usage
from ai4science.llm import ledger, pricing, routing

_ADAPTERS = {"anthropic": AnthropicAdapter, "openai": OpenAIAdapter, "gemini": GeminiAdapter}


def adapter_for(backend: str):
    cls = _ADAPTERS.get(backend)
    if cls is None:
        raise ValueError(f"no harness adapter for backend {backend!r}")
    return cls()


def make_meter(*, backend: str, model: str) -> Callable[[Usage], None]:
    def _meter(u: Usage) -> None:
        try:
            _src, _pid, wallet, mult = routing._select_source(backend)
            usage = {"input": u.input, "output": u.output, "total": u.total}
            cost = pricing.price_call(model, usage, price_multiplier=mult)
            ledger.record(agent="common-interactive", backend=backend, model=model,
                          wallet=wallet, usage=usage, cost=cost)
        except Exception:
            pass
    return _meter
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_factory.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire common mode in `commands/chat.py`**

In `_run_chat(...)`, when `mode == "common"`, build an `AgentSession` instead of the
`ClaudeSDKClient` path. Resolve the brand via routing's `orchestration` pool (default first
reachable; `/model` switches). Stream `on_text` to the terminal; `confirm` prompts per edit.

```python
# inside ai4science/commands/chat.py, common-mode branch of _run_chat
from ai4science.harness.session import AgentSession
from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.llm import routing

def _build_common_session(workspace, read_only, auto_yes, plan_mode):
    members = routing.ensemble_members("orchestration") or [("anthropic", "claude-opus-4-8")]
    backend, model = members[0]
    return AgentSession(
        adapter=adapter_for(backend), model=model, backend=backend,
        workspace=workspace, read_only=read_only or plan_mode, auto_yes=auto_yes,
        confirm=lambda name, args, preview: typer.confirm(f"Run {name}? {preview}", default=True),
        on_text=lambda t: typer.echo(t, nl=False),
        meter=make_meter(backend=backend, model=model),
    )
```

Drive the REPL loop: read a line → if slash, dispatch via existing `_handle_slash` (adding a
`/model` brand switch that calls `session.set_brand(adapter_for(b), m, b)` and a new
`session.meter = make_meter(...)`); else `session.run_turn(line)`.

- [ ] **Step 6: Add a chat integration test (stub adapter through the session)**

```python
# tests/test_chat_common_session.py
from pathlib import Path
from ai4science.harness.session import AgentSession
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done


def test_common_session_streams_text(tmp_path, capsys):
    sess = AgentSession(
        adapter=StubAdapter([[TextDelta("hello "), TextDelta("world"), Done("end")]]),
        model="stub", backend="anthropic", workspace=tmp_path,
        read_only=True, auto_yes=False,
        on_text=lambda t: print(t, end=""), meter=lambda u: None,
    )
    out = sess.run_turn("say hi")
    assert out == "hello world"
    assert "hello world" in capsys.readouterr().out
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_harness_factory.py tests/test_chat_common_session.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add ai4science/harness/adapters/factory.py ai4science/commands/chat.py tests/test_harness_factory.py tests/test_chat_common_session.py
git commit -m "feat(harness): adapter factory, ledger metering, common-mode REPL wiring"
```

---

### Task 11: Full suite green + parity doc

**Files:**
- Modify: `docs/CLAUDE_CODE_PARITY.md`
- Test: whole suite

- [ ] **Step 1: Run the entire suite**

Run: `python -m pytest -q`
Expected: PASS — all existing tests plus `tests/test_harness_*.py` and `tests/test_chat_common_session.py`.

- [ ] **Step 2: Manual cross-brand E2E (not CI)**

Run each, confirm streaming + a tool call + per-edit confirm behave identically:
```bash
ai4science chat --mode common               # default brand
# in REPL: /model gpt-5.5     -> same UX, OpenAI driving
# in REPL: /model gemini-3.1-pro-preview    -> same UX, Gemini driving
```

- [ ] **Step 3: Update the parity doc**

Append to `docs/CLAUDE_CODE_PARITY.md`:

```markdown
## Interactive common mode runs on a native brand-agnostic harness (2026-05-31)

Common mode's default is a single live streaming agent on `ai4science/harness/` — uniform
streaming, per-edit confirmation, and slash commands across Anthropic / ChatGPT / Gemini
(switch with `/model`, no UX change). See
`docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md`. The opt-in
ensemble (Plan 2) and parity extras — MCP, sub-agents, compaction (Plan 3) — follow.
```

- [ ] **Step 4: Commit**

```bash
git add docs/CLAUDE_CODE_PARITY.md
git commit -m "docs(parity): interactive common mode on the native harness"
```

---

## Self-review

- **Spec coverage:** experience-parity bar §3 — streaming (loop/adapters, Task 6–10), per-edit confirmation + sandbox (Task 4), read-only/auto-yes/plan modes (Task 4/6), `/model` brand switch (Task 10), accounting (Task 10). Native harness §5 — events (1), tools (2,3), permission gate (4), adapter interface + stub (5), loop+session (6), 3 adapters (7–9), REPL wiring (10). Deferred to Plan 3 and explicitly noted: MCP, sub-agents (`Task`), compaction, @mentions/images, custom slash commands. Ensemble is Plan 2.
- **Placeholder scan:** none — every code step is complete. Task 10 step 5 shows the exact wiring helper; the surrounding REPL edit references existing `_handle_slash`/`_run_chat` seams (real, from the interface audit).
- **Type consistency:** `Message`/`ToolSpec`/`TextDelta`/`ToolCall`/`Usage`/`Done` used identically across events, adapters, loop, session; `Tool(name, description, parameters, func, mutating)` and `Registry.specs()` consistent; `routing._select_source(backend) -> (source, provider_id, wallet, mult)`, `pricing.price_call(model, usage, price_multiplier)`, `ledger.record(agent, backend, model, wallet, usage, cost)` all match the audited signatures; `routing.ensemble_members` is added in the ensemble plan (Plan 2 Task 2) — Task 10 falls back to `[("anthropic","claude-opus-4-8")]` if absent, so Plan 1 does not hard-depend on Plan 2.

## Known limitations (carried to Plan 3)

1. Adapter `stream()` HTTP/SDK calls are validated by **manual E2E**, not CI (CI tests the pure translate/parse core). Record a real streamed response per provider as a fixture when convenient to widen coverage.
2. Input-token counts in the Anthropic adapter come from the final `message_delta`; the `input_tokens=0` fallback in `stream()` under-meters input until wired to the SDK's `message_start.usage`. Tighten in Plan 3.
3. MCP, sub-agents, compaction, @mentions, images, custom slash commands are Plan 3 — Plan 1 delivers the core live experience.
4. **`bash` is NOT path-sandboxed.** `PermissionGate` only inspects a tool's `path` arg; `bash` uses `cmd`, so a shell command can read/write `judge/`, `hidden_tests/`, or outside the workspace. In Plan 1 the only protection is that `bash` is **confirm-gated** — the human sees `$ <cmd>` and approves it (and `--yes`/ensemble auto-approve mode therefore trusts the model on shell). Plan 3 must add real bash sandboxing (cmd scan for protected-dir/parent-escape, or run bash in a bubblewrap/chroot workspace) to fully uphold the spec's moat guarantee (design §5).
5. The 50-iteration `run_loop` cap returns the accumulated text silently if hit — add a truncation signal/log in Plan 3.
6. **Resolved during execution (not a limitation):** the OpenAI empty-`choices` usage chunk (`IndexError`) and the Gemini synthetic-id tool round-trip desync were found in review and fixed; per-edit `confirm` is wired in `run_common_repl`.
