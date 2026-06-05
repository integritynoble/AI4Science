# AI4Science Agent Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three hard-coded harness modes (common/research/paper) with a plug-and-play registry of auto-discovered `AgentSpec`s, a `/mode` menu with search, a single tier-gated agent-dispatch tool, and the main-XOR-sub invariant — enforcing a two-tier moat (common = pure Claude Code; research/specific = PWM dataset).

**Architecture:** A new package `ai4science/harness/agents/` defines `AgentSpec` (the plug-in unit), a capability-bundle map, a discovery/lookup/search registry, and `build_registry_for(spec, *, is_subagent, ctx)` that assembles every agent from the Claude-Code base + its capability bundles + (only when *main*) a tier-gated `task` dispatch tool. `repl.py` and `chat.py` are rewired to drive sessions from specs instead of the deleted `build_*_registry` functions.

**Tech Stack:** Python 3, stdlib only (`dataclasses`, `importlib`, `pathlib`), pytest. No new third-party deps.

**Spec:** `docs/superpowers/specs/2026-06-04-agent-framework-design.md` (read it; this plan implements it). Note: the framework ships `common`, `research`, one example `specific` agent (`computational-imaging`), and the migrated generic helpers (`general-purpose`/`physics-reviewer`/`schema-validator`). `paper` and its `paper-review` bundle are added by the separate paper-mode plan (its `paper_tools` does not exist yet).

**Run tests with:** `PYTHONPATH=$(pwd) python3 -m pytest <path> -v` from `/home/spiritai/pwm/Physics_World_Model/AI4Science`. Baseline before starting: `354 passed, 4 skipped, 2 failed` — the 2 failures (`tests/test_chat.py::test_list_sessions_*`) are pre-existing (`import claude_agent_sdk`, SDK absent) and unrelated; leave them.

**Branch:** create `feat/agent-framework` off `main` before Task 1.

---

## File Structure

| File | Responsibility |
|---|---|
| `ai4science/harness/agents/__init__.py` | Package marker; re-export `AgentSpec`, `build_registry_for`, registry fns |
| `ai4science/harness/agents/spec.py` | `AgentSpec` frozen dataclass |
| `ai4science/harness/agents/capabilities.py` | `CAPABILITY_BUNDLES` map + `resolve_capability` |
| `ai4science/harness/agents/context.py` | `BuildContext` dataclass |
| `ai4science/harness/agents/registry.py` | discovery, `AGENT_REGISTRY`, `get`/`search`/`core_agents`/`specific_agents`, `build_registry_for`, `_can_dispatch`, `dispatchable_targets`, `_agent_dispatch_tool` |
| `ai4science/harness/agents/specs/*.py` | one `AGENT = AgentSpec(...)` per shipped agent |
| `ai4science/harness/repl.py` | (modify) build sessions via `build_registry_for`; `/mode` menu+search+switch; child session factory by spec |
| `ai4science/commands/chat.py` | (modify) `--mode` resolves against the registry; remove dead `_run_chat` |
| `docs/CLAUDE_CODE_PARITY.md` | (modify) document the framework + moat |
| `tests/test_harness_agents_*.py` | unit tests per module |

---

## Task 1: `AgentSpec` + capability bundles

**Files:**
- Create: `ai4science/harness/agents/__init__.py`
- Create: `ai4science/harness/agents/spec.py`
- Create: `ai4science/harness/agents/context.py`
- Create: `ai4science/harness/agents/capabilities.py`
- Test: `tests/test_harness_agents_capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_agents_capabilities.py
import pytest
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents import capabilities


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_agentspec_is_frozen():
    s = AgentSpec(name="x", tier="open", category="core", title="X", description="d")
    with pytest.raises(Exception):
        s.name = "y"


def test_pwm_actions_bundle_resolves(tmp_path):
    tools = capabilities.resolve_capability("pwm-actions", _ctx(tmp_path))
    names = {t.name for t in tools}
    assert {"pwm_status", "pwm_validate", "pwm_judge_cassi", "pwm_lookup_artifact"} <= names


def test_pwm_data_bundle_resolves(tmp_path):
    tools = capabilities.resolve_capability("pwm-data", _ctx(tmp_path))
    assert "pwm_solutions" in {t.name for t in tools}


def test_unknown_capability_raises(tmp_path):
    with pytest.raises(ValueError) as e:
        capabilities.resolve_capability("nope", _ctx(tmp_path))
    assert "nope" in str(e.value) and "pwm-data" in str(e.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_capabilities.py -v`
Expected: FAIL with `ModuleNotFoundError: ai4science.harness.agents`.

- [ ] **Step 3: Write minimal implementation**

```python
# ai4science/harness/agents/__init__.py
from ai4science.harness.agents.spec import AgentSpec  # noqa: F401
from ai4science.harness.agents.context import BuildContext  # noqa: F401
```

```python
# ai4science/harness/agents/spec.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple


@dataclass(frozen=True)
class AgentSpec:
    """One pluggable agent. Discovered from agents/specs/*.py (module attr AGENT)."""
    name: str                                   # unique id, e.g. "research"
    tier: str                                   # "open" (no PWM) | "science" (PWM moat)
    category: str                               # "core" | "specific" | "hidden"
    title: str                                  # short human label
    description: str                            # one-line; shown in /mode + dispatch enum
    keywords: Tuple[str, ...] = ()              # extra search terms
    system_prompt: Optional[str] = None
    capabilities: Tuple[str, ...] = ()          # bundle names added on top of the CC base
    allow_as_subagent: bool = True
    extra_tools: Optional[Callable] = None      # ctx -> list[Tool], optional custom tools
```

```python
# ai4science/harness/agents/context.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple


@dataclass
class BuildContext:
    """Everything builders/capabilities need that is not on the AgentSpec."""
    workspace: Path
    brand_provider: Callable[[], Tuple[str, str]]   # () -> (backend, model), live
    session_factory: Callable[..., object]          # (spec, ctx) -> AgentSession (child)
    read_only: bool = False
    auto_yes: bool = False
    enable_mcp: bool = True
    mcp_clients: Optional[List[object]] = None
```

```python
# ai4science/harness/agents/capabilities.py
from __future__ import annotations

from typing import Callable, Dict, List

from ai4science.harness.tools.base import Tool
from ai4science.harness.agents.context import BuildContext


def _pwm_actions(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness import mcp_pwm
    return list(mcp_pwm.pwm_tools())


def _pwm_data(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.research_tools import research_tools
    return list(research_tools())


# name -> provider(ctx) -> list[Tool]. The "paper-review" bundle is registered by
# the paper-mode plan (its paper_tools module does not exist yet).
CAPABILITY_BUNDLES: Dict[str, Callable[[BuildContext], List[Tool]]] = {
    "pwm-actions": _pwm_actions,
    "pwm-data": _pwm_data,
}


def resolve_capability(name: str, ctx: BuildContext) -> List[Tool]:
    try:
        provider = CAPABILITY_BUNDLES[name]
    except KeyError:
        valid = ", ".join(sorted(CAPABILITY_BUNDLES))
        raise ValueError(f"unknown capability bundle {name!r}; valid: {valid}")
    return provider(ctx)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_capabilities.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/__init__.py ai4science/harness/agents/spec.py \
        ai4science/harness/agents/context.py ai4science/harness/agents/capabilities.py \
        tests/test_harness_agents_capabilities.py
git commit -m "feat(agents): AgentSpec + BuildContext + capability bundles"
```

---

## Task 2: `build_registry_for` — base + capabilities (no dispatch yet)

**Files:**
- Create: `ai4science/harness/agents/registry.py` (partial — base build only)
- Test: `tests/test_harness_agents_build.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_agents_build.py
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_base_tools_present_for_every_agent(tmp_path):
    spec = AgentSpec(name="x", tier="open", category="core", title="X", description="d")
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    names = set(reg.names())
    assert {"read", "write", "edit", "grep", "glob", "bash"} <= names  # Claude Code first


def test_open_agent_has_no_pwm_tools(tmp_path):
    spec = AgentSpec(name="common", tier="open", category="core", title="C", description="d")
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    assert not any(n.startswith("pwm_") for n in reg.names())


def test_science_capabilities_add_tools(tmp_path):
    spec = AgentSpec(name="research", tier="science", category="core", title="R",
                     description="d", capabilities=("pwm-actions", "pwm-data"))
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    names = set(reg.names())
    assert "pwm_solutions" in names and "pwm_status" in names


def test_extra_tools_honored(tmp_path):
    from ai4science.harness.tools.base import Tool
    marker = Tool("marker", "d", {"type": "object", "properties": {}}, lambda ws: "ok")
    spec = AgentSpec(name="x", tier="open", category="core", title="X", description="d",
                     extra_tools=lambda ctx: [marker])
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    assert "marker" in reg.names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_build.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_registry_for'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ai4science/harness/agents/registry.py
from __future__ import annotations

from ai4science.harness.tools.base import Registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.capabilities import resolve_capability


def _claude_code_base(ctx: BuildContext) -> Registry:
    """Pure Claude Code: fs read/write/edit/grep/glob + bash + MCP. NO PWM."""
    from ai4science.harness.tools import default_registry
    reg = default_registry()
    if ctx.enable_mcp:
        from ai4science.harness.mcp_client import mcp_tools
        for client in (ctx.mcp_clients or []):
            for t in mcp_tools(client):
                reg.add(t)
    return reg


def build_registry_for(spec: AgentSpec, *, is_subagent: bool, ctx: BuildContext) -> Registry:
    reg = _claude_code_base(ctx)
    for cap in spec.capabilities:
        for t in resolve_capability(cap, ctx):
            reg.add(t)
    if spec.extra_tools:
        for t in spec.extra_tools(ctx):
            reg.add(t)
    # Dispatch tool is added in Task 4 (only when main). Left out here on purpose.
    return reg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_build.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/registry.py tests/test_harness_agents_build.py
git commit -m "feat(agents): build_registry_for (Claude-Code base + capability bundles)"
```

---

## Task 3: Spec discovery + lookup + search + the shipped spec files

**Files:**
- Modify: `ai4science/harness/agents/registry.py` (add discovery/lookup/search)
- Create: `ai4science/harness/agents/specs/__init__.py` (empty)
- Create: `ai4science/harness/agents/specs/common.py`
- Create: `ai4science/harness/agents/specs/general_purpose.py`
- Create: `ai4science/harness/agents/specs/physics_reviewer.py`
- Create: `ai4science/harness/agents/specs/schema_validator.py`
- Create: `ai4science/harness/agents/specs/research.py`
- Create: `ai4science/harness/agents/specs/computational_imaging.py`
- Test: `tests/test_harness_agents_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_agents_registry.py
import textwrap
import pytest
from ai4science.harness.agents import registry


def test_ships_expected_agents():
    registry.reload()  # default specs dir
    reg = registry.AGENT_REGISTRY
    assert {"common", "research", "computational-imaging",
            "general-purpose"} <= set(reg)
    assert reg["common"].tier == "open"
    assert reg["research"].tier == "science"
    assert reg["research"].system_prompt and "pwm_solutions" in reg["research"].system_prompt


def test_search_finds_by_keyword():
    registry.reload()
    hits = [s.name for s in registry.search("imaging")]
    assert "computational-imaging" in hits
    hits2 = [s.name for s in registry.search("cassi")]   # keyword match
    assert "computational-imaging" in hits2


def test_menu_partitions_core_vs_specific():
    registry.reload()
    assert "common" in {s.name for s in registry.core_agents()}
    assert "computational-imaging" in {s.name for s in registry.specific_agents()}
    # hidden helpers never show in the menu
    assert "general-purpose" not in {s.name for s in registry.core_agents()}
    assert "general-purpose" not in {s.name for s in registry.specific_agents()}


def test_duplicate_name_raises(tmp_path):
    d = tmp_path / "specs"
    d.mkdir()
    (d / "a.py").write_text(textwrap.dedent('''
        from ai4science.harness.agents.spec import AgentSpec
        AGENT = AgentSpec(name="dup", tier="open", category="core", title="A", description="d")
    '''))
    (d / "b.py").write_text(textwrap.dedent('''
        from ai4science.harness.agents.spec import AgentSpec
        AGENT = AgentSpec(name="dup", tier="open", category="core", title="B", description="d")
    '''))
    with pytest.raises(ValueError) as e:
        registry.reload(specs_dir=d)
    assert "dup" in str(e.value)
    registry.reload()  # restore default for other tests


def test_unknown_capability_in_spec_raises(tmp_path):
    d = tmp_path / "specs"
    d.mkdir()
    (d / "bad.py").write_text(textwrap.dedent('''
        from ai4science.harness.agents.spec import AgentSpec
        AGENT = AgentSpec(name="bad", tier="science", category="specific",
                          title="B", description="d", capabilities=("no-such-bundle",))
    '''))
    with pytest.raises(ValueError) as e:
        registry.reload(specs_dir=d)
    assert "no-such-bundle" in str(e.value)
    registry.reload()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_registry.py -v`
Expected: FAIL with `AttributeError: module 'ai4science.harness.agents.registry' has no attribute 'reload'`.

- [ ] **Step 3a: Write the spec files**

```python
# ai4science/harness/agents/specs/__init__.py
```

```python
# ai4science/harness/agents/specs/common.py
from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="common",
    tier="open",
    category="core",
    title="Common (Claude Code)",
    description="General coding assistant — Claude Code across brands. No PWM access.",
    keywords=("general", "code", "claude"),
    system_prompt=None,
)
```

```python
# ai4science/harness/agents/specs/general_purpose.py
from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="general-purpose",
    tier="open",
    category="hidden",
    title="General-purpose helper",
    description="A focused sub-agent for a delegated task.",
    system_prompt=("You are a focused sub-agent. Complete the delegated task and "
                   "report a concise result. Do not ask questions."),
)
```

```python
# ai4science/harness/agents/specs/physics_reviewer.py
from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="physics-reviewer",
    tier="open",
    category="hidden",
    title="Physics reviewer",
    description="Reviews a PWM submission for physical consistency.",
    system_prompt=("You are a physics reviewer. Inspect the workspace and report "
                   "concerns about physical consistency. You cannot override the "
                   "deterministic Physics Judge."),
)
```

```python
# ai4science/harness/agents/specs/schema_validator.py
from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="schema-validator",
    tier="open",
    category="hidden",
    title="Schema validator",
    description="Checks PWM artifacts against their schemas.",
    system_prompt="You validate PWM artifact schemas and report mismatches.",
)
```

```python
# ai4science/harness/agents/specs/research.py
from ai4science.harness.agents.spec import AgentSpec

RESEARCH_PROMPT = (
    "You are AI4Science in RESEARCH mode. You have the generic coding tools AND "
    "read-only access to the PWM registry: pwm_principles, pwm_principle, "
    "pwm_benchmarks, pwm_benchmark, pwm_solutions (registered SOTA solutions + "
    "scores per benchmark), pwm_overview. Use registered Principles, Specs, "
    "Benchmarks and Solutions to ground your work — consult pwm_solutions before "
    "proposing a new solution, and build on the best registered baselines. "
    "Mainnet/testnet status is shown via each artifact's chain_status."
)

AGENT = AgentSpec(
    name="research",
    tier="science",
    category="core",
    title="Research",
    description="PWM-grounded science agent: principles, specs, benchmarks, solutions.",
    keywords=("science", "pwm", "benchmark", "solution", "principle"),
    system_prompt=RESEARCH_PROMPT,
    capabilities=("pwm-actions", "pwm-data"),
)
```

```python
# ai4science/harness/agents/specs/computational_imaging.py
from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="computational-imaging",
    tier="science",
    category="specific",
    title="Computational imaging",
    description="Snapshot/compressive spectral imaging (CASSI), reconstruction, optics.",
    keywords=("cassi", "spectral", "optics", "reconstruction", "hyperspectral",
              "snapshot", "imaging", "inverse problem"),
    system_prompt=(
        "You are AI4Science specialized in computational imaging (snapshot "
        "compressive / spectral imaging such as CASSI, reconstruction, optical "
        "encoding). You have the generic coding tools AND read-only access to the "
        "PWM registry (pwm_principles/benchmarks/solutions/overview). Ground every "
        "design in the registered imaging principles, benchmarks and best solutions "
        "(consult pwm_solutions before proposing a new approach)."),
    capabilities=("pwm-actions", "pwm-data"),
)
```

- [ ] **Step 3b: Add discovery/lookup/search to `registry.py`**

Append to `ai4science/harness/agents/registry.py`:

```python
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional

from ai4science.harness.agents.capabilities import CAPABILITY_BUNDLES

_SPECS_DIR = Path(__file__).parent / "specs"
AGENT_REGISTRY: Dict[str, AgentSpec] = {}


def _load_spec_file(path: Path) -> AgentSpec:
    spec = importlib.util.spec_from_file_location(f"_agentspec_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    agent = getattr(module, "AGENT", None)
    if not isinstance(agent, AgentSpec):
        raise ValueError(f"{path} has no top-level AGENT: AgentSpec")
    return agent


def reload(specs_dir: Optional[Path] = None) -> Dict[str, AgentSpec]:
    """Discover all specs/*.py (each exposing AGENT) into AGENT_REGISTRY."""
    directory = Path(specs_dir) if specs_dir else _SPECS_DIR
    found: Dict[str, AgentSpec] = {}
    for path in sorted(directory.glob("*.py")):
        if path.name == "__init__.py":
            continue
        agent = _load_spec_file(path)
        if agent.name in found:
            raise ValueError(f"duplicate agent name {agent.name!r} ({path})")
        for cap in agent.capabilities:
            if cap not in CAPABILITY_BUNDLES:
                valid = ", ".join(sorted(CAPABILITY_BUNDLES))
                raise ValueError(
                    f"agent {agent.name!r} ({path}) uses unknown capability "
                    f"{cap!r}; valid: {valid}")
        found[agent.name] = agent
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(found)
    return AGENT_REGISTRY


def get(name: str) -> Optional[AgentSpec]:
    return AGENT_REGISTRY.get(name)


def core_agents() -> List[AgentSpec]:
    return [s for s in AGENT_REGISTRY.values() if s.category == "core"]


def specific_agents() -> List[AgentSpec]:
    return [s for s in AGENT_REGISTRY.values() if s.category == "specific"]


def search(query: str) -> List[AgentSpec]:
    q = (query or "").strip().lower()
    candidates = specific_agents()
    if not q:
        return candidates
    scored = []
    for s in candidates:
        hay = " ".join([s.name, s.title, s.description, " ".join(s.keywords)]).lower()
        pos = hay.find(q)
        if pos >= 0:
            scored.append((pos, s))
    return [s for _, s in sorted(scored, key=lambda t: t[0])]


reload()  # populate at import
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_registry.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/registry.py ai4science/harness/agents/specs/
git add tests/test_harness_agents_registry.py
git commit -m "feat(agents): spec discovery + lookup + search + shipped specs"
```

---

## Task 4: Tier-gated `task` dispatch tool + main-XOR-sub invariant

**Files:**
- Modify: `ai4science/harness/agents/registry.py` (add dispatch + wire into `build_registry_for`)
- Test: `tests/test_harness_agents_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_agents_dispatch.py
from ai4science.harness.agents import registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import (
    build_registry_for, dispatchable_targets, _can_dispatch)


def _ctx(tmp_path, recorder=None):
    def factory(*, spec, ctx):
        if recorder is not None:
            recorder.append(spec.name)
        class _S:  # minimal fake child session
            def run_turn(self, text, images=None):
                return f"child[{spec.name}] ran"
        return _S()
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=factory)


def test_can_dispatch_rule():
    open_a = AgentSpec(name="o", tier="open", category="hidden", title="o", description="d")
    sci_a = AgentSpec(name="s", tier="science", category="core", title="s", description="d")
    assert _can_dispatch(open_a, open_a) is True       # open target ok for anyone
    assert _can_dispatch(open_a, sci_a) is False       # open main cannot reach science
    assert _can_dispatch(sci_a, sci_a) is True         # science main can reach science
    assert _can_dispatch(sci_a, open_a) is True


def test_common_dispatch_excludes_science():
    registry.reload()
    targets = dispatchable_targets(registry.get("common"))
    assert "general-purpose" in targets
    assert "research" not in targets and "computational-imaging" not in targets


def test_research_dispatch_includes_science():
    registry.reload()
    targets = dispatchable_targets(registry.get("research"))
    assert {"research", "computational-imaging", "general-purpose"} <= set(targets)


def test_main_has_task_tool_subagent_does_not(tmp_path):
    registry.reload()
    research = registry.get("research")
    main = build_registry_for(research, is_subagent=False, ctx=_ctx(tmp_path))
    sub = build_registry_for(research, is_subagent=True, ctx=_ctx(tmp_path))
    assert "task" in main.names()
    assert "task" not in sub.names()          # invariant: sub cannot dispatch


def test_task_tool_runs_child(tmp_path):
    registry.reload()
    rec = []
    ctx = _ctx(tmp_path, recorder=rec)
    reg = build_registry_for(registry.get("research"), is_subagent=False, ctx=ctx)
    out = reg.get("task").func(tmp_path, subagent_type="general-purpose", prompt="hi")
    assert "child[general-purpose] ran" in out and rec == ["general-purpose"]


def test_task_tool_rejects_out_of_tier(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    out = reg.get("task").func(tmp_path, subagent_type="research", prompt="hi")
    assert "research" in out and "available" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_dispatch.py -v`
Expected: FAIL with `ImportError: cannot import name 'dispatchable_targets'`.

- [ ] **Step 3: Implement dispatch and wire it into `build_registry_for`**

Add to `ai4science/harness/agents/registry.py`:

```python
from ai4science.harness.tools.base import Tool


def _can_dispatch(main: AgentSpec, target: AgentSpec) -> bool:
    return target.tier == "open" or main.tier == "science"


def dispatchable_targets(main: AgentSpec) -> List[str]:
    return sorted(t.name for t in AGENT_REGISTRY.values()
                  if t.allow_as_subagent and _can_dispatch(main, t))


def _agent_dispatch_tool(main: AgentSpec, ctx: BuildContext) -> Optional[Tool]:
    targets = dispatchable_targets(main)
    if not targets:
        return None
    listed = ", ".join(targets)

    def _task(workspace, *, subagent_type: str, prompt: str) -> str:
        if subagent_type not in targets:
            return (f"[task] unknown subagent_type {subagent_type!r}; "
                    f"available: {listed}")
        child_spec = AGENT_REGISTRY[subagent_type]
        session = ctx.session_factory(spec=child_spec, ctx=ctx)
        sys = child_spec.system_prompt or ""
        return session.run_turn(f"{sys}\n\nTASK: {prompt}" if sys else prompt)

    return Tool(
        name="task",
        description=("Delegate a focused sub-task to a fresh sub-agent. "
                     f"subagent_type one of: {listed}."),
        parameters={"type": "object",
                    "properties": {"subagent_type": {"type": "string"},
                                   "prompt": {"type": "string"}},
                    "required": ["subagent_type", "prompt"]},
        func=_task, mutating=False,
    )
```

Then change the dispatch placeholder in `build_registry_for` (the comment line
`# Dispatch tool is added in Task 4 ...`) to:

```python
    if not is_subagent:
        tool = _agent_dispatch_tool(spec, ctx)
        if tool is not None:
            reg.add(tool)
    return reg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_dispatch.py tests/test_harness_agents_build.py -v`
Expected: PASS (build tests still green; dispatch tests pass).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/registry.py tests/test_harness_agents_dispatch.py
git commit -m "feat(agents): tier-gated task dispatch + main-XOR-sub invariant"
```

---

## Task 5: Wire `repl.py` to the registry (sessions, child factory, `/mode`)

**Files:**
- Modify: `ai4science/harness/repl.py`
- Test: `tests/test_harness_repl_modes.py`

**Context:** `run_common_repl` currently builds the main session in `_build_session()` (repl.py ~255-277) via `(registry_builder or build_common_registry)(workspace=…, session_factory=_child_session_factory, enable_pwm=True, enable_subagents=True)`, seeds `system_prompt` at history[0], and rebuilds on `/clear`. `/model` updates closure locals `active_backend/active_model` and calls `session.set_brand(...)`. We replace the registry construction with `build_registry_for(active_spec, is_subagent=False, ctx)`, make the child factory build sub-agent registries from specs, and add `/mode`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_repl_modes.py
from pathlib import Path
from ai4science.harness import repl
from ai4science.harness.agents import registry


def test_mode_menu_text_lists_core_and_specific():
    registry.reload()
    txt = repl._format_mode_menu()
    assert "common" in txt and "research" in txt and "specific" in txt.lower()


def test_mode_specific_search_text():
    registry.reload()
    txt = repl._format_specific_list("imaging")
    assert "computational-imaging" in txt


def test_build_main_registry_for_spec(tmp_path):
    registry.reload()
    ctx = repl._make_build_context(workspace=tmp_path,
                                   brand_provider=lambda: ("gemini", "m"))
    reg = repl._registry_for_spec(registry.get("common"), is_subagent=False, ctx=ctx)
    assert "task" in reg.names() and not any(n.startswith("pwm_") for n in reg.names())
    rreg = repl._registry_for_spec(registry.get("research"), is_subagent=False, ctx=ctx)
    assert "pwm_solutions" in rreg.names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_repl_modes.py -v`
Expected: FAIL with `AttributeError: module 'ai4science.harness.repl' has no attribute '_format_mode_menu'`.

- [ ] **Step 3: Implement repl helpers + rewire session building**

3a. Add imports near the top of `repl.py`:

```python
from ai4science.harness.agents import registry as agent_registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for
```

3b. Add module-level helpers (place after the existing prompt constants):

```python
def _make_build_context(*, workspace, brand_provider, session_factory=None,
                        read_only=False, auto_yes=False, mcp_clients=None) -> BuildContext:
    return BuildContext(workspace=workspace, brand_provider=brand_provider,
                        session_factory=session_factory, read_only=read_only,
                        auto_yes=auto_yes, mcp_clients=mcp_clients)


def _registry_for_spec(spec, *, is_subagent, ctx):
    return build_registry_for(spec, is_subagent=is_subagent, ctx=ctx)


def _format_mode_menu() -> str:
    lines = ["[modes]"]
    for s in agent_registry.core_agents():
        lines.append(f"  {s.name:<10} {s.description}")
    n = len(agent_registry.specific_agents())
    lines.append(f"  specific   ({n}) domain agents — /mode specific <query> to search")
    lines.append("  switch with: /mode <name>")
    return "\n".join(lines)


def _format_specific_list(query: str) -> str:
    hits = agent_registry.search(query)
    if not hits:
        return f"[modes] no specific agent matches {query!r}"
    return "\n".join([f"  {s.name:<24} {s.title}" for s in hits])
```

3c. Replace the registry construction inside `_build_session()`. The current call
is:

```python
            registry=(registry_builder or build_common_registry)(
                workspace=workspace,
                session_factory=_child_session_factory,
                enable_pwm=True,
                enable_subagents=True,
            ),
```

Replace it with (using the active spec + a BuildContext whose `session_factory`
builds spec-driven children):

```python
            registry=_registry_for_spec(
                active_spec, is_subagent=False,
                ctx=_make_build_context(
                    workspace=workspace,
                    brand_provider=lambda: (active_backend, active_model),
                    session_factory=_child_session_factory,
                    read_only=state["read_only"], auto_yes=state["auto_yes"],
                )),
```

3d. `active_spec` is the currently-selected agent. Initialize it where
`active_backend, active_model` are set (repl.py ~216) by resolving the mode:

```python
    active_spec = agent_registry.get(mode_label) or agent_registry.get("common")
```

(`mode_label` already exists as a parameter and equals the selected agent name.)

3d-bis. **Seed the MAIN session prompt from the active spec, not the static
`system_prompt` param** — so a `/mode` switch re-grounds correctly. In
`_build_session()`, change the existing seeding block:

```python
        if system_prompt:
            s.history.insert(0, Message(role="system", content=system_prompt))
```

to:

```python
        seed_prompt = active_spec.system_prompt or system_prompt
        if seed_prompt:
            s.history.insert(0, Message(role="system", content=seed_prompt))
```

The `system_prompt` param thus becomes a fallback only; Task 6 stops passing it.

3e. Update `_child_session_factory` to accept `(spec, ctx)` and build the child
registry as a sub-agent. Find the existing factory (it currently takes
`subagent_type`, `depth`). Replace its body so it builds a child `AgentSession`
with `registry=build_registry_for(spec, is_subagent=True, ctx=ctx)` and
`system_prompt=spec.system_prompt`, reusing the same adapter/model/workspace as
the parent (auto-approve gate, like today). Concretely:

```python
    def _child_session_factory(*, spec, ctx):
        child = AgentSession(
            adapter=adapter_for(active_backend),
            model=active_model,
            backend=active_backend,
            workspace=workspace,
            read_only=state["read_only"],
            auto_yes=True,                      # sub-agents auto-approve
            confirm=_confirm,
            on_text=on_text,
            meter=_make_wrapped_meter(active_backend, active_model),
            registry=build_registry_for(spec, is_subagent=True, ctx=ctx),
        )
        if spec.system_prompt:
            child.history.insert(0, Message(role="system", content=spec.system_prompt))
        return child
```

3f. Add the `/mode` command handler in the REPL slash-command dispatch, next to
the existing `/model` handler (which is handled inline because it needs the live
session). Insert:

```python
            if cmd == "/mode":
                arg = rest.strip()
                if not arg:
                    print(_format_mode_menu(), flush=True); continue
                parts = arg.split(maxsplit=1)
                if parts[0] == "specific":
                    print(_format_specific_list(parts[1] if len(parts) > 1 else ""),
                          flush=True); continue
                target = agent_registry.get(parts[0])
                if target is None:
                    print(f"[modes] unknown agent {parts[0]!r}; /mode to list",
                          flush=True); continue
                active_spec = target
                session = _build_session()      # rebuild with the new spec + its prompt
                print(f"[harness] switched mode: {target.name}", flush=True)
                continue
```

3g. The banner (repl.py ~286) prints `mode_label`. Keep it, but make it follow
the live agent: change the printed label to `active_spec.name` at session start,
and ensure the `/mode` switch updates the variable the banner/prompt uses.

3h. Keep `build_common_registry`/`build_research_registry` as thin shims for any
external importers (some tests import them) by leaving the functions in place but
having them delegate. Append at the bottom of their current definitions a comment
`# DEPRECATED: superseded by agents.build_registry_for` and do not call them from
`_build_session` anymore. (Task 6 updates the remaining caller, `chat.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_repl_modes.py tests/test_harness_research_registry.py -v`
Expected: the new mode tests PASS. If `tests/test_harness_research_registry.py`
asserts the old `build_research_registry` shape, update it to assert
`build_registry_for(agent_registry.get("research"), is_subagent=False, ctx)`
contains `pwm_solutions` and that `common` does not.

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/repl.py tests/test_harness_repl_modes.py tests/test_harness_research_registry.py
git commit -m "feat(repl): drive sessions from AgentSpec registry; /mode menu+search+switch"
```

---

## Task 6: Route `chat.py` through the registry; drop dead `_run_chat`

**Files:**
- Modify: `ai4science/commands/chat.py`
- Test: `tests/test_chat.py` (extend)

**Context:** `chat.py` currently has `if mode in ("common","research","paper"):` →
imports `run_common_repl`, `build_common_registry`, `build_research_registry`,
`build_paper_registry`*, `RESEARCH_PROMPT`, selects `rb`/`sp`/`mode_label`, calls
`run_common_repl(...)`. (*paper builders do not exist yet — see note.) After this
task, mode resolves against `AGENT_REGISTRY`; the registry is built inside
`run_common_repl` from `mode_label`, so `chat.py` only needs to pass the resolved
agent name as `mode_label` (and the agent's `system_prompt`).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_chat.py
def test_chat_mode_resolves_known_agent(monkeypatch, tmp_path):
    import ai4science.commands.chat as chat_mod
    captured = {}
    def fake_repl(workspace, **kw):
        captured.update(kw); captured["workspace"] = workspace
    monkeypatch.setattr(chat_mod, "run_common_repl", fake_repl)
    from typer.testing import CliRunner
    from ai4science.cli import app
    res = CliRunner().invoke(app, ["chat", "--mode", "computational-imaging",
                                   "--workspace", str(tmp_path)])
    assert res.exit_code == 0
    assert captured["mode_label"] == "computational-imaging"
    assert captured["system_prompt"]  # the spec's prompt was passed


def test_chat_unknown_mode_falls_back_to_common(monkeypatch, tmp_path):
    import ai4science.commands.chat as chat_mod
    captured = {}
    monkeypatch.setattr(chat_mod, "run_common_repl",
                        lambda workspace, **kw: captured.update(kw))
    from typer.testing import CliRunner
    from ai4science.cli import app
    res = CliRunner().invoke(app, ["chat", "--mode", "nonexistent",
                                   "--workspace", str(tmp_path)])
    assert res.exit_code == 0
    assert captured["mode_label"] == "common"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_chat.py::test_chat_mode_resolves_known_agent -v`
Expected: FAIL (current code rejects modes other than common/research/paper or
mishandles the resolution).

- [ ] **Step 3: Replace the mode block in `chat.py`**

Replace the body that begins `mode = (mode or os.environ.get("AI4SCIENCE_MODE") or "common").lower()`
and the following `if mode in (...)` dispatch with:

```python
    from ai4science.harness.agents import registry as agent_registry
    from ai4science.harness.repl import run_common_repl

    mode = (mode or os.environ.get("AI4SCIENCE_MODE") or "common").lower()
    spec = agent_registry.get(mode)
    if spec is None:
        names = ", ".join(sorted(agent_registry.AGENT_REGISTRY))
        console.print(f"[yellow]Unknown --mode {mode!r}; using 'common'. "
                      f"Available: {names}[/yellow]")
        spec = agent_registry.get("common")

    # The codex/non-claude one-shot rejection (if present) stays ABOVE this block.
    run_common_repl(
        workspace,
        read_only=read_only or plan,
        auto_yes=yes,
        model=model,
        system_prompt=spec.system_prompt,
        mode_label=spec.name,
    )
    return
```

Remove the now-unused `registry_builder=` argument plumbing: `run_common_repl`
selects the registry internally from `mode_label` (Task 5), so it no longer needs
`registry_builder`. Update `run_common_repl`'s signature to drop
`registry_builder` (and any `build_*_registry` imports in `chat.py`).

- [ ] **Step 4: Delete dead `_run_chat`**

Remove the `_run_chat` function and its only-callers' imports
(`no_subagents`/`no_mcp`/`enable_mcp` options that exist solely for it, plus the
top-level `import asyncio` if now unused). Verify nothing else references
`_run_chat`:

Run: `grep -rn "_run_chat\|registry_builder\|build_research_registry\|build_paper_registry" ai4science/ tests/`
Expected: no references remain (except possibly the deprecated shims in repl.py,
which are not called).

- [ ] **Step 5: Run tests + commit**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_chat.py -v`
Expected: PASS except the 2 pre-existing `test_list_sessions_*` failures.

```bash
git add ai4science/commands/chat.py ai4science/harness/repl.py tests/test_chat.py
git commit -m "feat(chat): resolve --mode against the agent registry; remove dead _run_chat"
```

---

## Task 7: Full suite, moat regression, live E2E, docs

**Files:**
- Modify: `docs/CLAUDE_CODE_PARITY.md`
- Test: `tests/test_harness_agents_moat.py`

- [ ] **Step 1: Write the moat regression test**

```python
# tests/test_harness_agents_moat.py
from ai4science.harness.agents import registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_common_is_walled_off(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    names = set(reg.names())
    # no PWM tools of any kind, no paper_review
    assert not any(n.startswith("pwm_") for n in names)
    assert "paper_review" not in names
    # task tool present but cannot reach science agents
    assert "task" in names
    out = reg.get("task").func(tmp_path, subagent_type="research", prompt="x")
    assert "available" in out.lower() and "research" in out


def test_science_agents_hold_the_moat(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("research"), is_subagent=False, ctx=_ctx(tmp_path))
    assert "pwm_solutions" in reg.names()
    # and a science main CAN dispatch another science agent
    from ai4science.harness.agents.registry import dispatchable_targets
    assert "computational-imaging" in dispatchable_targets(registry.get("research"))
```

- [ ] **Step 2: Run the moat test + full suite**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_agents_moat.py -v`
Expected: PASS (2 passed).

Run: `PYTHONPATH=$(pwd) python3 -m pytest -q`
Expected: all green except the 2 pre-existing `test_list_sessions_*` failures.
Fix any other red caused by the migration before proceeding.

- [ ] **Step 3: Live E2E (network) — driven by the controller, not the implementer**

The implementer SKIPS this; the controller runs it after review:

```bash
WS=$(mktemp -d)
printf '/mode\n/mode specific imaging\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode common --workspace "$WS" 2>&1 | tail -20
# Expect: the /mode menu lists common/research/specific; /mode specific imaging
# lists computational-imaging.

WS2=$(mktemp -d)
printf '/model gemini gemini-3.1-pro-preview\nList your available tools. Do you have pwm_solutions?\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode common --workspace "$WS2" 2>&1 | tail -20
# Expect: common lists read/write/edit/bash/grep/glob/task — NO pwm_* tools.

WS3=$(mktemp -d)
printf '/model gemini gemini-3.1-pro-preview\nUse pwm_solutions on benchmark L3-003 and name the best solution.\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode research --workspace "$WS3" 2>&1 | tail -20
# Expect: research calls pwm_solutions(L3-003) -> MST-L score_q 0.95.
```

- [ ] **Step 4: Update docs**

Append a "Agent framework" section to `docs/CLAUDE_CODE_PARITY.md` describing:
the `/mode` menu + search, plug-and-play `AgentSpec` discovery, the two tiers
(common open / research+specific science) and the moat, the tier-gated `task`
dispatch, and the main-XOR-sub invariant. Note that `paper` and `paper-review`
are added by the paper-mode plan.

- [ ] **Step 5: Commit**

```bash
git add tests/test_harness_agents_moat.py docs/CLAUDE_CODE_PARITY.md
git commit -m "test(agents): moat regression + docs for the agent framework"
```

---

## After all tasks

1. Dispatch a final whole-implementation reviewer over `main..feat/agent-framework`.
2. Controller runs the Task 7 Step 3 live E2E and captures output.
3. Use `superpowers:finishing-a-development-branch` → merge to `main` locally
   (the established pattern), after confirming the suite is green (minus the 2
   pre-existing failures).
4. Update memory `project_agent_framework.md` → built & merged.
5. Next: the paper-mode pipeline plan plugs `paper` in as the `paper-review`
   capability + `paper` spec.
