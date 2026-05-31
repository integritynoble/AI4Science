# Plan 3b — Sub-agents (Task tool) + MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two remaining big Claude-Code capabilities to the native harness: **sub-agents** (a `Task` tool that delegates a sub-task to a fresh nested `AgentSession`) and **MCP** (expose the existing in-process PWM MCP tools, and connect to external stdio MCP servers) — reconnecting common mode to the science layer (`pwm_validate`, `pwm_judge_cassi`, …).

**Architecture:** Built on the harness (`ai4science/harness/`). A `harness/subagents.py` defines named sub-agent profiles (system prompt + tool allow-list) and a `make_task_tool(...)` that returns a `Tool` whose `func` spins up a nested `AgentSession` (auto-approve, depth-guarded) and returns its result. A `harness/mcp_pwm.py` wraps the existing async `pwm_*` functions (`ai4science/agents/mcp_pwm.py`) as harness `Tool`s. A `harness/mcp_client.py` speaks the MCP stdio JSON-RPC protocol to external servers and wraps their tools. `harness/repl.py` + `session` assemble the combined registry (core ∪ pwm ∪ mcp ∪ task) and add `/agents` and `/mcp` info commands.

**Tech Stack:** Python 3 (`asyncio`, `subprocess`, JSON-RPC over stdio), pytest + monkeypatch, existing `ai4science.harness` and `ai4science.agents.mcp_pwm` (deterministic `pwm_*` coroutines).

**Spec:** `docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md` (§10 Plan 3b). Predecessors: Plan 1, 3a, 3d (all merged).

**Scope note:** This plan adds sub-agents + MCP. It does NOT add `@mentions`/images (Plan 3c). Full OAuth/HTTP MCP transports are out of scope — only stdio MCP servers (the common case) plus the in-process PWM tools.

## File structure

| File | Responsibility |
|---|---|
| `ai4science/harness/subagents.py` (create) | sub-agent profiles + `make_task_tool` |
| `ai4science/harness/mcp_pwm.py` (create) | wrap `agents/mcp_pwm` `pwm_*` coroutines as harness Tools |
| `ai4science/harness/mcp_client.py` (create) | stdio MCP JSON-RPC client + `mcp_tools(client)` |
| `ai4science/harness/repl.py` (modify) | assemble combined registry; `/agents`, `/mcp` commands |
| `tests/test_harness_*.py` | one test file per unit |

---

### Task 1: Sub-agent `Task` tool (nested session, depth guard)

**Files:**
- Create: `ai4science/harness/subagents.py`
- Test: `tests/test_harness_subagents.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_subagents.py
from pathlib import Path
from ai4science.harness.subagents import SUBAGENTS, make_task_tool
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done


def test_subagents_registry_has_profiles():
    assert "general" in SUBAGENTS
    assert "system_prompt" in SUBAGENTS["general"]


def test_task_tool_runs_nested_session(tmp_path):
    # the child session is built by an injected factory; here it returns a
    # stub that answers "child-done".
    def _factory(*, subagent_type, depth):
        from ai4science.harness.session import AgentSession
        return AgentSession(
            adapter=StubAdapter([[TextDelta("child-done"), Done("end")]]),
            model="stub", backend="anthropic", workspace=tmp_path,
            read_only=False, auto_yes=True, on_text=lambda t: None, meter=lambda u: None,
        )
    tool = make_task_tool(session_factory=_factory, depth=0, max_depth=2)
    assert tool.name == "task"
    out = tool.func(tmp_path, subagent_type="general", prompt="do a thing")
    assert "child-done" in out


def test_task_tool_depth_guard(tmp_path):
    tool = make_task_tool(session_factory=lambda **k: None, depth=2, max_depth=2)
    out = tool.func(tmp_path, subagent_type="general", prompt="x")
    assert "depth" in out.lower() and "max" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/spiritai/pwm/Physics_World_Model/AI4Science && python -m pytest tests/test_harness_subagents.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `subagents.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

from ai4science.harness.tools.base import Tool

# Sub-agent profiles. Reuse the PWM sub-agent intents (see agents/subagents.py)
# but as harness-native system prompts. `tools` (optional) is an allow-list.
SUBAGENTS: Dict[str, Dict] = {
    "general": {
        "description": "A general-purpose worker for a focused sub-task.",
        "system_prompt": "You are a focused sub-agent. Complete the delegated "
                         "task and report a concise result. Do not ask questions.",
    },
    "physics-reviewer": {
        "description": "Reviews a PWM submission for physical consistency.",
        "system_prompt": "You are a physics reviewer. Inspect the workspace and "
                         "report concerns about physical consistency. You cannot "
                         "override the deterministic Physics Judge.",
    },
    "schema-validator": {
        "description": "Checks PWM artifacts against their schemas.",
        "system_prompt": "You validate PWM artifact schemas and report mismatches.",
    },
}

MAX_SUBAGENT_DEPTH = 2


def make_task_tool(*, session_factory: Callable[..., object], depth: int,
                   max_depth: int = MAX_SUBAGENT_DEPTH) -> Tool:
    """Return a `task` Tool that delegates to a nested AgentSession.

    session_factory(subagent_type=str, depth=int) -> AgentSession (auto-approve).
    Depth-guarded to prevent unbounded recursion.
    """
    names = ", ".join(sorted(SUBAGENTS))

    def _task(workspace: Path, *, subagent_type: str, prompt: str) -> str:
        if depth >= max_depth:
            return f"[task] refused: max sub-agent depth ({max_depth}) reached"
        if subagent_type not in SUBAGENTS:
            return f"[task] unknown subagent_type {subagent_type!r}; available: {names}"
        session = session_factory(subagent_type=subagent_type, depth=depth + 1)
        sys_prompt = SUBAGENTS[subagent_type]["system_prompt"]
        return session.run_turn(f"{sys_prompt}\n\nTASK: {prompt}")

    return Tool(
        name="task",
        description=("Delegate a focused sub-task to a fresh sub-agent. "
                     f"subagent_type one of: {names}."),
        parameters={"type": "object",
                    "properties": {"subagent_type": {"type": "string"},
                                   "prompt": {"type": "string"}},
                    "required": ["subagent_type", "prompt"]},
        func=_task, mutating=False,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_subagents.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/subagents.py tests/test_harness_subagents.py
git commit -m "feat(harness): Task sub-agent tool (nested session + depth guard)"
```

---

### Task 2: PWM MCP tools as native harness tools

**Files:**
- Create: `ai4science/harness/mcp_pwm.py`
- Test: `tests/test_harness_mcp_pwm.py`

Wrap the existing deterministic coroutines in `ai4science/agents/mcp_pwm.py` (`pwm_validate`, `pwm_judge_cassi`, `pwm_status`, `pwm_lookup_artifact` — each `async (args: dict) -> dict`) as synchronous harness `Tool`s (run the coroutine, JSON-dump the result). These are read/verify tools (non-mutating) and need no LLM.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_mcp_pwm.py
from ai4science.harness import mcp_pwm


def test_pwm_tools_registered():
    tools = {t.name: t for t in mcp_pwm.pwm_tools()}
    assert "pwm_status" in tools and "pwm_judge_cassi" in tools
    assert tools["pwm_status"].mutating is False


def test_pwm_status_runs(tmp_path):
    tools = {t.name: t for t in mcp_pwm.pwm_tools()}
    out = tools["pwm_status"].func(tmp_path)   # returns a JSON string
    assert isinstance(out, str) and "{" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_mcp_pwm.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `mcp_pwm.py`**

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, List

from ai4science.harness.tools.base import Tool
from ai4science.agents import mcp_pwm as _pwm   # the deterministic coroutines

_STR = {"type": "string"}

# (name, description, extra-properties) for each PWM tool. workspace is injected.
_SPECS = [
    ("pwm_status", "Workspace status: artifacts present + reports.", {}),
    ("pwm_validate", "Run ai4science validate on the workspace.", {}),
    ("pwm_judge_cassi", "Run the deterministic CASSI Physics Judge.", {}),
    ("pwm_lookup_artifact", "Read a PWM artifact by canonical name.",
     {"artifact": _STR}),
]


def _wrap(coro: Callable, name: str) -> Callable[..., str]:
    def _tool(workspace: Path, **args) -> str:
        call_args = dict(args)
        call_args.setdefault("workspace", str(workspace))
        try:
            result = asyncio.run(coro(call_args))
        except Exception as exc:
            return f"[{name}] error: {exc}"
        return json.dumps(result, indent=2, default=str)
    return _tool


def pwm_tools() -> List[Tool]:
    out = []
    for name, desc, extra in _SPECS:
        coro = getattr(_pwm, name)
        props = {"workspace": _STR, **extra}
        out.append(Tool(name, desc,
                        {"type": "object", "properties": props}, _wrap(coro, name),
                        mutating=False))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_mcp_pwm.py -v`
Expected: PASS (2 tests). If `pwm_status` needs a specific arg shape, adjust the `call_args` defaults to match `agents/mcp_pwm.pwm_status`'s expectations (read that function first).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/mcp_pwm.py tests/test_harness_mcp_pwm.py
git commit -m "feat(harness): expose PWM MCP tools (validate/judge/status/lookup) natively"
```

---

### Task 3: External stdio MCP client

**Files:**
- Create: `ai4science/harness/mcp_client.py`
- Test: `tests/test_harness_mcp_client.py`

A minimal MCP stdio client: spawn a server subprocess, JSON-RPC `initialize` → `tools/list` → `tools/call`. The transport is injectable so CI tests it against an in-process fake (no real server). `mcp_tools(client)` wraps each remote tool as a harness `Tool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_mcp_client.py
from ai4science.harness.mcp_client import MCPClient, mcp_tools


class _FakeTransport:
    """In-process fake MCP server: answers initialize / tools/list / tools/call."""
    def __init__(self):
        self._tools = [{"name": "echo", "description": "echo text",
                        "inputSchema": {"type": "object",
                                        "properties": {"text": {"type": "string"}}}}]

    def request(self, method, params):
        if method == "initialize":
            return {"capabilities": {}}
        if method == "tools/list":
            return {"tools": self._tools}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "echo:" + params["arguments"]["text"]}]}
        raise AssertionError(method)


def test_client_lists_and_calls(tmp_path):
    c = MCPClient(transport=_FakeTransport(), server="demo")
    c.initialize()
    specs = c.list_tools()
    assert specs[0]["name"] == "echo"
    result = c.call_tool("echo", {"text": "hi"})
    assert result == "echo:hi"


def test_mcp_tools_wraps_with_namespace(tmp_path):
    c = MCPClient(transport=_FakeTransport(), server="demo")
    c.initialize()
    tools = mcp_tools(c)
    assert tools[0].name == "mcp__demo__echo"
    out = tools[0].func(tmp_path, text="yo")
    assert out == "echo:yo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_mcp_client.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `mcp_client.py`**

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai4science.harness.tools.base import Tool


class StdioTransport:
    """JSON-RPC over a server subprocess's stdin/stdout (newline-delimited)."""
    def __init__(self, cmd: List[str], cwd: Optional[Path] = None) -> None:
        self.proc = subprocess.Popen(
            cmd, cwd=str(cwd) if cwd else None,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self._id = 0

    def request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp.get("result", {})

    def close(self) -> None:
        try:
            self.proc.terminate()
        except Exception:
            pass


class MCPClient:
    def __init__(self, *, transport, server: str) -> None:
        self.transport = transport
        self.server = server
        self._tools: List[Dict] = []

    def initialize(self) -> None:
        self.transport.request("initialize", {"protocolVersion": "2024-11-05",
                                              "capabilities": {}, "clientInfo": {"name": "ai4science"}})

    def list_tools(self) -> List[Dict]:
        self._tools = self.transport.request("tools/list", {}).get("tools", [])
        return self._tools

    def call_tool(self, name: str, args: Dict[str, Any]) -> str:
        res = self.transport.request("tools/call", {"name": name, "arguments": args})
        # MCP returns content blocks; join text blocks.
        parts = [b.get("text", "") for b in res.get("content", []) if b.get("type") == "text"]
        return "".join(parts)


def mcp_tools(client: MCPClient) -> List[Tool]:
    out = []
    for spec in (client._tools or client.list_tools()):
        name = spec["name"]
        qualified = f"mcp__{client.server}__{name}"

        def _make(tool_name: str):
            def _call(workspace: Path, **args) -> str:
                return client.call_tool(tool_name, args)
            return _call

        out.append(Tool(qualified, spec.get("description", ""),
                        spec.get("inputSchema", {"type": "object"}),
                        _make(name), mutating=True))   # remote tools may mutate
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_mcp_client.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/mcp_client.py tests/test_harness_mcp_client.py
git commit -m "feat(harness): stdio MCP client + tool wrapping (namespaced mcp__server__tool)"
```

---

### Task 4: Assemble the combined registry + REPL info commands

**Files:**
- Modify: `ai4science/harness/repl.py` (build registry = core ∪ pwm ∪ task; `/agents`, `/mcp`)
- Test: `tests/test_harness_registry_assembly.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_registry_assembly.py
from ai4science.harness.repl import build_common_registry


def test_registry_includes_core_pwm_and_task(tmp_path):
    reg = build_common_registry(workspace=tmp_path,
                                session_factory=lambda **k: None,
                                enable_pwm=True, enable_subagents=True)
    names = set(reg.names())
    assert {"read", "edit", "bash"}.issubset(names)        # core
    assert "pwm_status" in names                            # pwm
    assert "task" in names                                  # sub-agents


def test_registry_can_disable(tmp_path):
    reg = build_common_registry(workspace=tmp_path,
                                session_factory=lambda **k: None,
                                enable_pwm=False, enable_subagents=False)
    names = set(reg.names())
    assert "pwm_status" not in names and "task" not in names
    assert "read" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harness_registry_assembly.py -v`
Expected: FAIL — `build_common_registry` missing.

- [ ] **Step 3: Add `build_common_registry` to `repl.py` and use it**

Add (module-level) in `ai4science/harness/repl.py`:
```python
def build_common_registry(*, workspace, session_factory, enable_pwm=True,
                          enable_subagents=True, mcp_clients=None):
    from ai4science.harness.tools import default_registry
    reg = default_registry()
    if enable_pwm:
        from ai4science.harness import mcp_pwm
        for t in mcp_pwm.pwm_tools():
            reg.add(t)
    if enable_subagents:
        from ai4science.harness.subagents import make_task_tool
        reg.add(make_task_tool(session_factory=session_factory, depth=0))
    for client in (mcp_clients or []):
        from ai4science.harness.mcp_client import mcp_tools
        for t in mcp_tools(client):
            reg.add(t)
    return reg
```
Then in `run_common_repl`, build the session's registry via `build_common_registry(...)` instead of the bare `default_registry()` (the `session_factory` makes a child AgentSession for the `task` tool using the same adapter/model, `auto_yes=True`, and the SAME registry-building call at `depth+1`). Add `/agents` (lists `SUBAGENTS`) and `/mcp` (lists connected servers' tools) to `_dispatch_slash` or inline.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_harness_registry_assembly.py tests/test_harness_repl.py tests/test_harness_repl_slash.py -v`
Expected: PASS (new + existing repl tests green).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/repl.py tests/test_harness_registry_assembly.py
git commit -m "feat(harness): assemble core+PWM+sub-agent+MCP registry; /agents /mcp"
```

---

### Task 5: Full suite green + parity doc

- [ ] **Step 1:** `python -m pytest -q` — all green except the 2 pre-existing `test_list_sessions_*` env failures. Fix any harness regression.
- [ ] **Step 2:** Update `docs/CLAUDE_CODE_PARITY.md`: mark Plan 3b DONE (sub-agents via `Task`, PWM MCP tools native, stdio MCP client). Note remaining: Plan 3c (`@mentions`, images); HTTP/OAuth MCP transports out of scope.
- [ ] **Step 3:** Commit: `git commit -m "docs(parity): Plan 3b sub-agents + MCP landed"`.

---

## Self-review

- **Coverage:** sub-agents (Task 1), PWM MCP native (Task 2), external stdio MCP (Task 3), registry assembly + REPL wiring (Task 4). `@mentions`/images deferred to Plan 3c; HTTP/OAuth MCP out of scope — stated, not dropped.
- **Placeholder scan:** every step has concrete code. Task 2 step 4 notes to read `agents/mcp_pwm.pwm_status` for the exact arg shape — a real grounding step, not a placeholder.
- **Type consistency:** `Tool(name, description, parameters, func, mutating)` used throughout; `session.run_turn(prompt) -> str`; MCP `call_tool -> str`; the `task` tool's `session_factory(subagent_type=, depth=)` contract matches Task 4's registry assembly.

## Known limitations
1. The `task` sub-agent shares the parent's brand/adapter; per-sub-agent model selection is a follow-on.
2. MCP client is stdio + synchronous request/response only (no server-initiated notifications, no HTTP/OAuth).
3. PWM tool arg shapes must match `agents/mcp_pwm` — verify per tool during Task 2.
