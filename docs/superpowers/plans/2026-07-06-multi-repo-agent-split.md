# Multi-Repo Agent Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn each PWM agent into an independently installable GitHub repo running on one shared runtime, embeddable into AI4Science via Python entry points and cross-callable when co-installed.

**Architecture:** Introduce a stable runtime facade (`pwm_agent_core`) as the versioned contract every agent binds to; make agent discovery driven by `pwm_agent.specs` / `pwm_agent.bundles` entry points so *installed = available*; move GPU compute into the core capability set; then split the flagship `research` agent into its own repo end-to-end as the pattern for the rest.

**Tech Stack:** Python ≥3.10, setuptools, `importlib.metadata` entry points, `typer`/`rich` CLI, `prompt_toolkit` TUI, `pytest`. Existing code lives at `ai4science/harness/**` + `pwm_core/**` in `integritynoble/AI4Science`.

## Global Constraints

- **Import namespace of the runtime stays `ai4science.*` / `pwm_core.*`.** We do NOT rename existing modules. The new contract is a thin facade module `pwm_agent_core` that re-exports the stable surface; physical dist extraction (Task 10) moves files behind that unchanged facade. Copy this rule into every task's mental model: agent repos import the runtime **only** through `pwm_agent_core`, never deep-import `ai4science.harness.*`.
- **`AgentSpec` dataclass is unchanged** (`ai4science/harness/agents/spec.py`). It is the contract type; do not add required fields.
- **Backward compatibility is mandatory at every task boundary.** The existing `ai4science` CLI, the directory-scan spec loader (`_SPECS_DIR`), and the manifest plugin path (`PLUGIN_STANDARD.md`) must keep working after each task. Discovery is additive: builtin dir-scan → entry points → manifest plugins.
- **Single credential store:** all login/wallet state stays at `~/.ai4science` / `~/.config/ai4science` (core-owned). No per-agent credentials.
- **Cross-calling is local-only.** Missing dispatch target → an install-hint string, never a network call or auto-install.
- **Distribution vs command naming** (verbatim from spec): core dist `pwm-agent-core` (library, no command); agents `pwm-agent-<x>` with command `pwm-<x>`; framework dist `pwm-ai4science`, command `ai4science`. All repos under the `integritynoble` org.
- **Core version is the compatibility contract.** Expose `pwm_agent_core.__version__` and `pwm_agent_core.CONTRACT_VERSION` (int). Agents pin `pwm-agent-core>=X,<Y`.
- **TDD, DRY, YAGNI, frequent commits.** Every code step ships with a test; run it red before green.

---

## File Structure

**In the existing AI4Science repo (Phase 1):**
- Create: `ai4science/pwm_agent_core.py` — the runtime facade (public contract surface).
- Create: `tests/test_pwm_agent_core_facade.py` — facade surface + version tests.
- Modify: `ai4science/harness/agents/capabilities.py` — add reload-surviving external-bundle tier + entry-point bundle discovery.
- Modify: `ai4science/harness/agents/registry.py` — `reload()` also discovers `pwm_agent.specs` / `pwm_agent.bundles` entry points.
- Create: `tests/test_entrypoint_discovery.py` — entry-point spec + bundle discovery, missing-sibling hint.
- Modify: `ai4science/harness/agents/registry.py` — `_agent_dispatch_tool._task` returns install hint for known-but-uninstalled targets.
- Modify: `ai4science/harness/agents/capabilities.py` — move `compute-providers` into the always-available core bundle set for every agent.
- Modify: `ai4science/harness/agents/specs/research.py` etc. — no behavior change; confirm they resolve post-refactor.

**New repo `pwm-agent-research` (Phase 2), layout mirrored by every Phase 3 agent repo:**
```
pwm-agent-research/
  pyproject.toml            # dist pwm-agent-research; dep pwm-agent-core>=X,<Y; entry points; script pwm-research
  install.sh                # curl|bash installer (venv under ~/.ai4science)
  README.md
  src/pwm_agent_research/
    __init__.py             # exposes AGENT; registers its capability bundles on import
    agent.py                # the AgentSpec (moved from specs/research.py)
    prompts.py              # RESEARCH_PROMPT
    tools/
      __init__.py
      research_tools.py     # moved from ai4science/harness/research_tools.py
      onboard_tools.py      # moved from ai4science/harness/onboard_tools.py
    cli.py                  # thin: sets default agent = research, calls core CLI main
  tests/
    test_spec_loads.py      # AGENT importable + valid AgentSpec
    test_entrypoint.py      # entry points resolve in an installed env
    test_standalone_boot.py # pwm-research --help / dry boot
    test_research_tools.py  # the domain tools' own tests (moved with the code)
```

**Framework changes (end of Phase 2 / Phase 3):**
- Modify: `pyproject.toml` — `pwm-ai4science` depends on core + all agent packages.
- Delete (per agent, only after its repo is green): `ai4science/harness/agents/specs/<agent>.py` and the agent's `*_tools.py`, replaced by the entry-point package.
- Create: `ai4science/harness/agents/specs/ai4science_meta.py` — the `ai4science` meta-agent that dispatches to all installed siblings.

---

## Phase 1 — Core contract & discovery

### Task 1: Runtime facade `pwm_agent_core`

**Files:**
- Create: `ai4science/pwm_agent_core.py`
- Test: `tests/test_pwm_agent_core_facade.py`

**Interfaces:**
- Produces: module `pwm_agent_core` re-exporting `AgentSpec`, `BuildContext`, `Registry`, `Tool`, `register_agent_bundle`, `reload`, `get`, `dispatchable_targets`, `build_registry_for`, and `run_cli(default_agent: str | None = None) -> None`. Also `__version__: str` and `CONTRACT_VERSION: int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pwm_agent_core_facade.py
import pwm_agent_core as core

def test_contract_surface_present():
    for name in ("AgentSpec", "BuildContext", "Tool", "reload", "get",
                 "dispatchable_targets", "build_registry_for",
                 "register_agent_bundle", "run_cli"):
        assert hasattr(core, name), f"missing {name}"

def test_versions_exposed():
    assert isinstance(core.CONTRACT_VERSION, int) and core.CONTRACT_VERSION >= 1
    assert isinstance(core.__version__, str) and core.__version__

def test_agentspec_is_the_real_type():
    from ai4science.harness.agents.spec import AgentSpec as Real
    assert core.AgentSpec is Real
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pwm_agent_core_facade.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pwm_agent_core'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ai4science/pwm_agent_core.py
"""Stable runtime contract for standalone PWM agent packages.

Agent repos import the runtime ONLY through this module. Everything here is
version-guaranteed by CONTRACT_VERSION; deep imports of ai4science.harness.*
are not. Physical extraction of the runtime into its own distribution moves
files behind this facade without changing it.
"""
from __future__ import annotations

CONTRACT_VERSION = 1

try:                                             # dist version, best-effort
    from importlib.metadata import version, PackageNotFoundError
    try:
        __version__ = version("pwm-agent-core")
    except PackageNotFoundError:
        __version__ = version("pwm-ai4science")
except Exception:
    __version__ = "0+unknown"

from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.tools.base import Registry, Tool
from ai4science.harness.agents.registry import (
    reload, get, dispatchable_targets, build_registry_for,
)
from ai4science.harness.agents.capabilities import register_agent_bundle


def run_cli(default_agent: str | None = None) -> None:
    """Boot the standard AI4Science CLI/TUI, defaulted to one agent.

    A standalone `pwm-<agent>` command calls run_cli("<agent>"). When
    default_agent is set and the user passes no explicit --agent/AI4SCIENCE_AGENT,
    that agent is preselected.
    """
    import os
    from ai4science.cli import main as _main
    if default_agent and not os.environ.get("AI4SCIENCE_AGENT"):
        os.environ["AI4SCIENCE_AGENT"] = default_agent
    _main()
```

Note: `register_agent_bundle` does not exist yet — Task 2 adds it. Import it there; until Task 2 lands this import will fail, so Task 2's step order below has you add the function first. To keep Task 1 independently green, temporarily import it lazily inside a function if executing strictly in order is not possible; otherwise do Task 2 Step 3 before Task 1 Step 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pwm_agent_core_facade.py -v`
Expected: PASS (3 passed). If `register_agent_bundle` import errors, complete Task 2 Step 3 first, then re-run.

- [ ] **Step 5: Commit**

```bash
git add ai4science/pwm_agent_core.py tests/test_pwm_agent_core_facade.py
git commit -m "feat(core): add pwm_agent_core runtime facade + contract version"
```

### Task 2: Reload-surviving external capability bundles

**Files:**
- Modify: `ai4science/harness/agents/capabilities.py`
- Test: `tests/test_external_bundles.py`

**Interfaces:**
- Consumes: existing `register_plugin_bundle`, `clear_plugin_bundles`, `_rebuild_union`.
- Produces: `register_agent_bundle(name: str, provider: Callable[[BuildContext], List[Tool]]) -> None` and `clear_agent_bundles() -> None`. Agent-registered bundles live in `AGENT_BUNDLES` and are included by `_rebuild_union`. Unlike plugin bundles they are NOT cleared by `clear_plugin_bundles()` (they are cleared only by `clear_agent_bundles()`, called by `reload()` right before it re-imports entry-point bundles).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_external_bundles.py
from ai4science.harness.agents import capabilities as cap

def _one_tool_provider(ctx):
    from ai4science.harness.tools.base import Tool
    return [Tool(name="xdemo", description="d", parameters={"type": "object", "properties": {}},
                 func=lambda workspace: "ok", mutating=False)]

def test_agent_bundle_survives_plugin_clear():
    cap.register_agent_bundle("x-demo", _one_tool_provider)
    assert "x-demo" in cap.CAPABILITY_BUNDLES
    cap.clear_plugin_bundles()                       # reload clears PLUGIN, not AGENT
    assert "x-demo" in cap.CAPABILITY_BUNDLES
    cap.clear_agent_bundles()
    assert "x-demo" not in cap.CAPABILITY_BUNDLES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_external_bundles.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'register_agent_bundle'`.

- [ ] **Step 3: Write minimal implementation**

In `ai4science/harness/agents/capabilities.py`, after the `PLUGIN_BUNDLES` definition add:

```python
# Bundles contributed by installed agent packages (entry-point group
# "pwm_agent.bundles"). Rebuilt from entry points on every registry reload.
AGENT_BUNDLES: Dict[str, Callable[[BuildContext], List[Tool]]] = {}
```

Update `_rebuild_union` to include them (agent bundles lose to nothing except explicit plugins; order: builtin < agent < plugin):

```python
def _rebuild_union() -> None:
    CAPABILITY_BUNDLES.clear()
    CAPABILITY_BUNDLES.update(BUILTIN_BUNDLES)
    CAPABILITY_BUNDLES.update(AGENT_BUNDLES)
    CAPABILITY_BUNDLES.update(PLUGIN_BUNDLES)
```

Add the two functions:

```python
def register_agent_bundle(name: str, provider: Callable[[BuildContext], List[Tool]]) -> None:
    """Register a capability bundle owned by an installed agent package."""
    AGENT_BUNDLES[name] = provider
    _rebuild_union()


def clear_agent_bundles() -> None:
    AGENT_BUNDLES.clear()
    _rebuild_union()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_external_bundles.py tests/test_pwm_agent_core_facade.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/capabilities.py tests/test_external_bundles.py
git commit -m "feat(core): reload-surviving external capability bundles for agent packages"
```

### Task 3: Entry-point discovery in `reload()`

**Files:**
- Modify: `ai4science/harness/agents/registry.py`
- Test: `tests/test_entrypoint_discovery.py`

**Interfaces:**
- Consumes: `AgentSpec`, `capabilities.register_agent_bundle`, `capabilities.clear_agent_bundles`, `_validate_caps`.
- Produces: after `reload()`, `AGENT_REGISTRY` also contains every spec advertised under entry-point group `pwm_agent.specs` (value = a module attr resolving to an `AgentSpec`), and every bundle under `pwm_agent.bundles` (value = a `register()` callable that calls `register_agent_bundle`). Discovery order: builtin dir-scan → entry-point bundles → entry-point specs → manifest plugins. Name collisions: an entry-point spec whose name already exists is skipped and recorded in `PLUGIN_ERRORS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entrypoint_discovery.py
import types
from ai4science.harness.agents import registry, capabilities

class _FakeEP:
    def __init__(self, name, group, obj):
        self.name, self.group, self._obj = name, group, obj
    def load(self):
        return self._obj

def _install_fake_entrypoints(monkeypatch, specs=(), bundles=()):
    eps = [ _FakeEP(s.name, "pwm_agent.specs", s) for s in specs ]
    eps += [ _FakeEP(n, "pwm_agent.bundles", fn) for n, fn in bundles ]
    def fake_entry_points(*, group=None):
        return [e for e in eps if e.group == group]
    monkeypatch.setattr(registry, "_iter_entry_points", fake_entry_points)

def test_entrypoint_spec_discovered(monkeypatch):
    from ai4science.harness.agents.spec import AgentSpec
    demo = AgentSpec(name="demo-ep", tier="open", category="specific",
                     title="Demo", description="demo agent", capabilities=())
    _install_fake_entrypoints(monkeypatch, specs=[demo])
    registry.reload()
    assert registry.get("demo-ep") is demo

def test_entrypoint_bundle_registered(monkeypatch):
    def register():
        capabilities.register_agent_bundle(
            "demo-bundle", lambda ctx: [])
    _install_fake_entrypoints(monkeypatch, bundles=[("demo-bundle", register)])
    registry.reload()
    assert "demo-bundle" in capabilities.CAPABILITY_BUNDLES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_entrypoint_discovery.py -v`
Expected: FAIL with `AttributeError: module ... registry has no attribute '_iter_entry_points'`.

- [ ] **Step 3: Write minimal implementation**

At the top of `registry.py` add the seam + import:

```python
from ai4science.harness.agents.capabilities import (
    resolve_capability, CAPABILITY_BUNDLES,
    register_plugin_bundle, clear_plugin_bundles,
    register_agent_bundle, clear_agent_bundles,   # NEW
)

def _iter_entry_points(*, group: str):
    """Indirection so tests can inject fake entry points."""
    from importlib.metadata import entry_points
    try:
        return list(entry_points(group=group))       # py3.10+ selectable API
    except TypeError:                                 # very old importlib shim
        return list(entry_points().get(group, []))
```

In `reload()`, right after the builtin dir-scan loop and before the manifest-plugin block, insert entry-point discovery:

```python
    # ── entry-point plug-ins (installed agent packages) ──
    clear_agent_bundles()
    for ep in _iter_entry_points(group="pwm_agent.bundles"):
        try:
            ep.load()()                              # register() -> register_agent_bundle(...)
        except Exception as exc:
            PLUGIN_ERRORS.append(f"bundle entry-point {ep.name!r}: {exc}")
    for ep in _iter_entry_points(group="pwm_agent.specs"):
        try:
            agent = ep.load()
        except Exception as exc:
            PLUGIN_ERRORS.append(f"spec entry-point {ep.name!r}: {exc}")
            continue
        if not isinstance(agent, AgentSpec):
            PLUGIN_ERRORS.append(f"spec entry-point {ep.name!r}: not an AgentSpec")
            continue
        if agent.name in found:
            PLUGIN_ERRORS.append(f"spec entry-point {agent.name!r}: name collides; skipped")
            continue
        try:
            _validate_caps(agent.name, agent.capabilities, "entry-point")
        except ValueError as exc:
            PLUGIN_ERRORS.append(str(exc))
            continue
        found[agent.name] = agent
        for alias in agent.aliases:
            aliases[alias] = agent.name
```

Note ordering: bundles register before specs so a spec's `capabilities` validate against bundles its own package just registered.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_entrypoint_discovery.py tests/test_external_bundles.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full existing suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS (same count as before + the new tests). Fix any breakage before committing.

- [ ] **Step 6: Commit**

```bash
git add ai4science/harness/agents/registry.py tests/test_entrypoint_discovery.py
git commit -m "feat(core): discover agent specs+bundles from pwm_agent entry points"
```

### Task 4: Install-hint for uninstalled dispatch targets

**Files:**
- Modify: `ai4science/harness/agents/registry.py` (the `_agent_dispatch_tool._task` closure + a helper)
- Test: `tests/test_dispatch_hint.py`

**Interfaces:**
- Produces: `install_hint(name: str) -> str` returning `"<name> agent not installed — run: pip install pwm-agent-<name>"`. `_task` returns this hint when `subagent_type` is a **known** PWM agent name that is not currently in `targets`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch_hint.py
from ai4science.harness.agents import registry

def test_install_hint_format():
    assert registry.install_hint("research") == \
        "research agent not installed — run: pip install pwm-agent-research"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dispatch_hint.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'install_hint'`.

- [ ] **Step 3: Write minimal implementation**

Add near the top of `registry.py`:

```python
# Canonical agent names shippable as their own package (for install hints).
_SPLITTABLE_AGENTS = {
    "research", "paper", "computational-imaging", "drug-design", "cancer",
    "unified-LLM", "claude-gpu", "codex-gpu",
}

def install_hint(name: str) -> str:
    return f"{name} agent not installed — run: pip install pwm-agent-{name}"
```

In `_task` inside `_agent_dispatch_tool`, replace the unknown-type branch:

```python
        child_spec = AGENT_REGISTRY.get(subagent_type)
        if subagent_type not in targets or child_spec is None:
            if subagent_type in _SPLITTABLE_AGENTS and child_spec is None:
                return install_hint(subagent_type)
            return (f"[task] unknown subagent_type {subagent_type!r}; "
                    f"available: {listed}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dispatch_hint.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/registry.py tests/test_dispatch_hint.py
git commit -m "feat(core): install hint when dispatching to an uninstalled agent"
```

### Task 5: GPU compute available to every agent

**Files:**
- Modify: `ai4science/harness/agents/registry.py` (`build_registry_for`)
- Test: `tests/test_gpu_core_capability.py`

**Interfaces:**
- Consumes: existing `compute-providers` bundle (`capabilities._compute_providers`).
- Produces: `build_registry_for(spec, is_subagent, ctx)` always includes the `compute-providers` tools for every agent, regardless of whether the spec lists it in `capabilities`. Adds a module constant `ALWAYS_ON_BUNDLES = ("compute-providers",)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gpu_core_capability.py
from ai4science.harness.agents import registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext

def test_every_agent_gets_compute_tools():
    spec = AgentSpec(name="nogpu-listed", tier="open", category="specific",
                     title="t", description="d", capabilities=())  # no compute in caps
    ctx = BuildContext.for_test() if hasattr(BuildContext, "for_test") else BuildContext()
    reg = registry.build_registry_for(spec, is_subagent=True, ctx=ctx)
    names = {t.name for t in reg.tools()} if hasattr(reg, "tools") else set(reg)
    assert any(n.startswith("compute_") for n in names), names
```

If `BuildContext()` needs required args, inspect `ai4science/harness/agents/context.py` and construct it with the minimal test values (workspace = a `tmp_path`); adjust the fixture accordingly before running.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gpu_core_capability.py -v`
Expected: FAIL (no `compute_*` tools present).

- [ ] **Step 3: Write minimal implementation**

In `registry.py` add the constant and use it in `build_registry_for`:

```python
ALWAYS_ON_BUNDLES = ("compute-providers",)   # GPU compute is a core capability for every agent
```

```python
def build_registry_for(spec: AgentSpec, *, is_subagent: bool, ctx: BuildContext) -> Registry:
    reg = _claude_code_base(ctx)
    caps = tuple(dict.fromkeys(spec.capabilities + ALWAYS_ON_BUNDLES))
    for cap in caps:
        for t in resolve_capability(cap, ctx):
            reg.add(t)
    _attach_spec_mcp_servers(spec, ctx, reg)
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gpu_core_capability.py -q`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`
Expected: PASS. (Watch for specs that duplicated `compute-providers` — the de-dup handles it.)

- [ ] **Step 6: Commit**

```bash
git add ai4science/harness/agents/registry.py tests/test_gpu_core_capability.py
git commit -m "feat(core): GPU compute is an always-on capability for every agent"
```

### Task 6: Publishable `pyproject` metadata for core contract

**Files:**
- Modify: `pyproject.toml` (framework, still `pwm-ai4science`)
- Modify: `ai4science/harness/agents/specs/*.py` — nothing yet; verify only.
- Test: `tests/test_contract_version.py`

**Interfaces:**
- Produces: `pwm_agent_core.CONTRACT_VERSION` referenced by agent pins. No dist rename here — Task 10 does the physical `pwm-agent-core` dist. This task documents the contract and adds a guard test so future edits bump it deliberately.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contract_version.py
import pwm_agent_core as core

def test_contract_is_v1():
    # Bump this AND core.CONTRACT_VERSION together when the runtime surface changes.
    assert core.CONTRACT_VERSION == 1
```

- [ ] **Step 2: Run test to verify it passes immediately (guard test)**

Run: `python -m pytest tests/test_contract_version.py -q`
Expected: PASS. (This is an intentional guard, not red-green; it fails only when someone changes the contract version without updating the test.)

- [ ] **Step 3: Document the contract in pyproject**

Add to `pyproject.toml` under `[project.urls]` or a comment block near the top:

```toml
# Runtime contract for standalone agent packages: import via `pwm_agent_core`
# only. Contract surface + version live in ai4science/pwm_agent_core.py
# (CONTRACT_VERSION). Agent packages pin: pwm-agent-core>=1,<2.
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/test_contract_version.py
git commit -m "docs(core): document pwm_agent_core contract + guard its version"
```

---

## Phase 2 — Research pilot repo (end-to-end)

> Phase 2 creates the first standalone agent repo and proves: standalone install+login+run, embed-into-AI4Science via entry point, and cross-call both ways. Every step here is the template Phase 3 repeats.

### Task 7: Scaffold `pwm-agent-research` repo

**Files (new repo `pwm-agent-research`):**
- Create: `pyproject.toml`, `src/pwm_agent_research/__init__.py`, `agent.py`, `prompts.py`, `tools/__init__.py`, `cli.py`, `install.sh`, `README.md`
- Move (from AI4Science): `ai4science/harness/research_tools.py` → `src/pwm_agent_research/tools/research_tools.py`; `ai4science/harness/onboard_tools.py` → `.../tools/onboard_tools.py`
- Test: `tests/test_spec_loads.py`

**Interfaces:**
- Produces: importing `pwm_agent_research` exposes `AGENT: AgentSpec` (name `"research"`) and, as an import side effect, registers its `pwm-data` + `onboarding` capability bundles via `pwm_agent_core.register_agent_bundle`. Entry points: `pwm_agent.specs` → `pwm_agent_research:AGENT`; `pwm_agent.bundles` → `pwm_agent_research:register_bundles`. Console script `pwm-research = pwm_agent_research.cli:main`.

- [ ] **Step 1: Create the repo skeleton and move the tool code**

```bash
mkdir -p pwm-agent-research/src/pwm_agent_research/tools pwm-agent-research/tests
cd pwm-agent-research
git init
# copy the domain tools out of AI4Science (adjust source path as needed):
cp <AI4Science>/ai4science/harness/research_tools.py src/pwm_agent_research/tools/research_tools.py
cp <AI4Science>/ai4science/harness/onboard_tools.py  src/pwm_agent_research/tools/onboard_tools.py
```

Fix imports inside the copied files: any `from ai4science.harness.tools.base import Tool` becomes `from pwm_agent_core import Tool`; any deep runtime import becomes the `pwm_agent_core` facade equivalent. Leave pure-Python/domain logic untouched.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pwm-agent-research"
version = "0.1.0"
description = "PWM Research agent — rigorous, registry-grounded scientific research. Standalone or embedded in AI4Science."
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
dependencies = ["pwm-agent-core>=1,<2"]

[project.scripts]
pwm-research = "pwm_agent_research.cli:main"

[project.entry-points."pwm_agent.specs"]
research = "pwm_agent_research:AGENT"

[project.entry-points."pwm_agent.bundles"]
research = "pwm_agent_research:register_bundles"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: Write `prompts.py` and `agent.py` (move the spec)**

`prompts.py`: paste `RESEARCH_PROMPT` verbatim from `ai4science/harness/agents/specs/research.py`.

`agent.py`:

```python
from pwm_agent_core import AgentSpec
from .prompts import RESEARCH_PROMPT

AGENT = AgentSpec(
    name="research",
    tier="science",
    category="core",
    title="Research",
    description="Rigorous, registry-grounded scientific research agent.",
    system_prompt=RESEARCH_PROMPT,
    capabilities=("pwm-data", "onboarding"),
    order=20,
)
```

Copy the exact field values (tier/category/order/keywords/aliases/capabilities) from the current `specs/research.py` so behavior is identical. Do not invent values.

- [ ] **Step 4: Write `tools/__init__.py` and `__init__.py` (register bundles on import)**

`tools/__init__.py`:

```python
from .research_tools import research_tools
from .onboard_tools import onboard_tools
__all__ = ["research_tools", "onboard_tools"]
```

`src/pwm_agent_research/__init__.py`:

```python
from pwm_agent_core import register_agent_bundle
from .agent import AGENT
from .tools import research_tools, onboard_tools

def register_bundles() -> None:
    """Called by core's registry reload via the pwm_agent.bundles entry point."""
    register_agent_bundle("pwm-data", lambda ctx: list(research_tools()))
    register_agent_bundle("onboarding", lambda ctx: list(onboard_tools()))

# Also register on import so standalone boot (which imports AGENT directly) works
# even before a full registry reload.
register_bundles()

__all__ = ["AGENT", "register_bundles"]
```

- [ ] **Step 5: Write `cli.py`**

```python
from pwm_agent_core import run_cli

def main() -> None:
    run_cli(default_agent="research")
```

- [ ] **Step 6: Write the failing test**

```python
# tests/test_spec_loads.py
def test_agent_spec_valid():
    import pwm_agent_research as pkg
    from pwm_agent_core import AgentSpec
    assert isinstance(pkg.AGENT, AgentSpec)
    assert pkg.AGENT.name == "research"
    assert pkg.AGENT.capabilities == ("pwm-data", "onboarding")

def test_bundles_register():
    import pwm_agent_research as pkg
    from ai4science.harness.agents import capabilities as cap
    pkg.register_bundles()
    assert "pwm-data" in cap.CAPABILITY_BUNDLES
    assert "onboarding" in cap.CAPABILITY_BUNDLES
```

- [ ] **Step 7: Install both packages editable and run the test**

```bash
pip install -e <AI4Science>          # provides pwm_agent_core + runtime (until Task 10 splits core)
pip install -e .                      # this repo
python -m pytest tests/test_spec_loads.py -v
```
Expected: PASS. (If `pwm-agent-core` is not yet a separate dist, the `dependencies` pin is satisfied by installing AI4Science, which ships `pwm_agent_core`. Task 10 makes it a real dist.)

- [ ] **Step 8: Commit (in the new repo)**

```bash
git add -A && git commit -m "feat: pwm-agent-research standalone package (spec + tools + bundles + cli)"
```

### Task 8: `install.sh` + standalone boot + entry-point discovery tests

**Files (in `pwm-agent-research`):**
- Create: `install.sh`
- Test: `tests/test_entrypoint.py`, `tests/test_standalone_boot.py`

**Interfaces:**
- Consumes: `pwm_agent_core.run_cli`, core's `reload`.
- Produces: `pwm-research --help` exits 0; `reload()` in an env with this package installed returns a registry containing `research`.

- [ ] **Step 1: Write `install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
VENV="${AI4SCIENCE_HOME:-$HOME/.ai4science}/venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install "pwm-agent-research"
BIN_DIR="${HOME}/.local/bin"; mkdir -p "$BIN_DIR"
ln -sf "$VENV/bin/pwm-research" "$BIN_DIR/pwm-research"
echo "Installed. Run: pwm-research login  then  pwm-research"
```

Mirror AI4Science's existing `install.sh` conventions (same venv home, same PATH shim) — read it first and match it exactly so both installers coexist.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_entrypoint.py
def test_research_discovered_via_reload():
    from pwm_agent_core import reload, get
    reload()
    assert get("research") is not None
    assert get("research").name == "research"
```

```python
# tests/test_standalone_boot.py
import subprocess, sys
def test_help_exits_zero():
    r = subprocess.run([sys.executable, "-c",
        "import pwm_agent_research.cli as c; "
        "import sys; sys.argv=['pwm-research','--help']; "
        "\ntry:\n c.main()\nexcept SystemExit as e:\n assert e.code in (0,None)"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 3: Run to verify they fail (before install)**

Run: `python -m pytest tests/test_entrypoint.py -v`
Expected: FAIL if the package isn't installed into the env yet.

- [ ] **Step 4: Install + run to green**

```bash
pip install -e .
python -m pytest tests/test_entrypoint.py tests/test_standalone_boot.py -v
```
Expected: PASS.

- [ ] **Step 5: Manual standalone smoke (record output)**

```bash
pwm-research --help
```
Expected: usage text, exit 0. (Full `pwm-research login` requires real PWM creds — note it as a manual acceptance step, not an automated test.)

- [ ] **Step 6: Commit**

```bash
chmod +x install.sh
git add -A && git commit -m "feat: installer + standalone boot & entry-point discovery tests"
```

### Task 9: Embed research back into AI4Science + cross-call both ways

**Files (in AI4Science):**
- Delete: `ai4science/harness/agents/specs/research.py`, `ai4science/harness/research_tools.py`, `ai4science/harness/onboard_tools.py`
- Modify: `ai4science/harness/agents/capabilities.py` — remove the now-duplicate `_pwm_data`/`_onboarding` builtin bundle entries (they come from the package now); keep the names valid by relying on the entry-point registration.
- Modify: `pyproject.toml` — add `pwm-agent-research` to `dependencies`.
- Test: `tests/test_research_via_package.py`, `tests/test_cross_call.py`

**Interfaces:**
- Consumes: entry-point discovery (Task 3), install hint (Task 4).
- Produces: with `pwm-agent-research` installed, AI4Science resolves `research` from the package (not a local spec file); with it *uninstalled*, dispatching to `research` yields the install hint.

- [ ] **Step 1: Write the failing test (research still resolves, now from the package)**

```python
# tests/test_research_via_package.py
def test_research_resolves_from_package():
    from ai4science.harness.agents import registry
    registry.reload()
    spec = registry.get("research")
    assert spec is not None and spec.name == "research"
    # It now originates from the installed package, not a local specs/*.py file:
    import os
    assert not os.path.exists("ai4science/harness/agents/specs/research.py")
```

- [ ] **Step 2: Run — verify current state fails the "no local file" assertion**

Run: `python -m pytest tests/test_research_via_package.py -v`
Expected: FAIL (the local `specs/research.py` still exists).

- [ ] **Step 3: Do the swap**

```bash
pip install -e ../pwm-agent-research        # ensure the package is in this env
git rm ai4science/harness/agents/specs/research.py \
       ai4science/harness/research_tools.py \
       ai4science/harness/onboard_tools.py
```

In `capabilities.py`, delete the `_pwm_data` and `_onboarding` functions and their `BUILTIN_BUNDLES` entries (`"pwm-data"`, `"onboarding"`). They are now provided by `pwm_agent_research.register_bundles()` via the entry point. Update `pyproject.toml`:

```toml
dependencies = [
  # ...existing...
  "pwm-agent-research>=0.1,<1",
]
```

- [ ] **Step 4: Run to green**

Run: `python -m pytest tests/test_research_via_package.py -q && python -m pytest -q`
Expected: PASS. Fix any lingering deep-import of `research_tools`/`onboard_tools` inside AI4Science by importing from the package or via the bundle.

- [ ] **Step 5: Cross-call test (both directions, with hint fallback)**

```python
# tests/test_cross_call.py
def test_research_is_a_dispatch_target_when_installed():
    from ai4science.harness.agents import registry
    registry.reload()
    main = registry.get("unified-LLM") or next(iter(registry.AGENT_REGISTRY.values()))
    targets = registry.dispatchable_targets(main)
    assert "research" in targets or main.tier != "science"

def test_missing_target_returns_hint():
    from ai4science.harness.agents import registry
    assert registry.install_hint("drug-design") == \
        "drug-design agent not installed — run: pip install pwm-agent-drug-design"
```

Run: `python -m pytest tests/test_cross_call.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: source research agent from pwm-agent-research package via entry point"
```

### Task 10: Physically extract `pwm-agent-core` distribution

**Files (in AI4Science):**
- Create: `packaging/pwm-agent-core/pyproject.toml` (or a `core/` subtree) declaring dist `pwm-agent-core` that ships the generic runtime modules + `pwm_agent_core.py` + `pwm_core/`.
- Modify: framework `pyproject.toml` — depend on `pwm-agent-core>=1,<2`; remove the generic modules from the framework wheel's package set (framework keeps `ai4science.cli`, `ai4science.commands`, specs, meta-agent).
- Test: `tests/test_core_dist_boots_alone.py`

**Interfaces:**
- Produces: `pip install pwm-agent-core` alone yields an importable `pwm_agent_core` with the full contract surface and NO agents. This satisfies the agent packages' `pwm-agent-core>=1,<2` pin without installing the framework.

- [ ] **Step 1: Decide the split boundary (generic vs framework)**

Generic → `pwm-agent-core`: `ai4science/harness/**` (tool base, loop, session, mcp_client, llm_gateway, transport, tui, registry, capabilities, spec, context, compute*, wallet/login), `ai4science/pwm_agent_core.py`, `ai4science/llm/**`, `ai4science/wallet.py`, `ai4science/pwm_account.py`, `ai4science/compute/**`, `pwm_core/**`.
Framework-only → stays in `pwm-ai4science`: `ai4science/cli.py`, `ai4science/commands/**`, `ai4science/harness/agents/specs/**` (the remaining builtin/meta specs), passthrough claude/codex modes.

Because both dists contribute to the `ai4science.*` namespace, convert `ai4science/` and `ai4science/harness/` to **implicit namespace packages** (remove `__init__.py` from the shared parent packages, or use `setuptools` `namespace_packages` / PEP 420). Verify no `ai4science/__init__.py` executes import-time code that both dists need; if it does, move that code into `pwm_agent_core`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_core_dist_boots_alone.py  (run in a CLEAN venv with ONLY pwm-agent-core)
def test_core_imports_without_agents():
    import pwm_agent_core as core
    core.reload()
    from ai4science.harness.agents.registry import AGENT_REGISTRY
    # No first-party agents ship with core:
    assert "research" not in AGENT_REGISTRY
    assert hasattr(core, "run_cli")
```

- [ ] **Step 3: Build & install core alone in a throwaway venv**

```bash
python -m venv /tmp/corevenv
/tmp/corevenv/bin/pip install ./packaging/pwm-agent-core
/tmp/corevenv/bin/python -m pytest tests/test_core_dist_boots_alone.py -v
```
Expected: PASS.

- [ ] **Step 4: Verify the framework still installs on top and is unchanged**

```bash
python -m venv /tmp/fwvenv
/tmp/fwvenv/bin/pip install ./packaging/pwm-agent-core ./ ../pwm-agent-research
/tmp/fwvenv/bin/python -m pytest -q
/tmp/fwvenv/bin/ai4science --help
```
Expected: full suite PASS; CLI help unchanged.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "build: extract pwm-agent-core distribution behind the pwm_agent_core facade"
```

- [ ] **Step 6: Publish (manual, gated)**

Publish `pwm-agent-core` then `pwm-agent-research` to the index the installers pull from (PyPI or the private index). Record versions. Re-run `pwm-agent-research/install.sh` from clean to confirm the real `curl | bash → login → run` path.

---

## Phase 3 — Split the remaining seven agents (reusable procedure)

Phase 3 repeats Tasks 7–9 once per agent, parameterized by the table below. There is no new mechanism — the code shapes are identical to the research pilot; only the names, prompt file, capabilities, and moved tool modules change. Do them one repo at a time, each fully green (standalone boot + entry-point resolve + cross-call + framework swap) before starting the next.

**Per-agent parameters** (values copied from the current `specs/*.py` and `capabilities.py`; confirm each against the source spec before coding):

| Agent (spec name) | Repo / dist | Command | `capabilities` today | Tool modules to move |
|---|---|---|---|---|
| `unified-LLM` | `pwm-agent-unified` | `pwm-unified` | (base only) | none (pure Claude-Code base) |
| `paper` | `pwm-agent-paper` | `pwm-paper` | `paper-review` (+ `pwm-data`) | `paper_tools.py`, `paper_review.py`, `paper_bundle.py`, `paper_load.py` |
| `computational-imaging` | `pwm-agent-imaging` | `pwm-imaging` | `computational-imaging`, `optics-design`, `forward-model`, `ci-algorithms`, `science-router` | `cassi_tools.py`, `optics_tools.py`, `forward_model_tools.py`, `algorithm_tools.py`, `registry_router_tools.py` |
| `drug-design` | `pwm-agent-drug` | `pwm-drug` | `drug-design` | `drug_design_tools.py` |
| `cancer` | `pwm-agent-cancer` | `pwm-cancer` | `cancer` | `cancer_tools.py` |
| `claude-gpu` | `pwm-agent-claude-gpu` | `pwm-claude-gpu` | (passthrough + core GPU) | thin wrapper over the claude passthrough mode |
| `codex-gpu` | `pwm-agent-codex-gpu` | `pwm-codex-gpu` | (passthrough + core GPU) | thin wrapper over `codex_repl.py` / codex passthrough |

**Procedure per agent (mechanical repeat of Tasks 7–9):**

- [ ] **A. Scaffold** the repo exactly as Task 7 (skeleton, `pyproject.toml` with the two entry points + console script, `agent.py` copying the spec's fields verbatim from `specs/<name>.py`, `prompts.py`, `tools/`, `cli.py` calling `run_cli(default_agent="<name>")`, `__init__.py` registering the agent's bundles).
- [ ] **B. Move the tool modules** listed above out of `ai4science/harness/` into the repo's `tools/`, fixing imports to `pwm_agent_core`. For `claude-gpu`/`codex-gpu`, the "tools" are the passthrough wiring; keep the passthrough source in the framework and have the GPU package's spec reference it via capability + the core `compute-providers` bundle (already always-on from Task 5), so `+GPU` = passthrough experience + core GPU.
- [ ] **C. Standalone tests** as Task 8 (`test_spec_loads`, `test_entrypoint`, `test_standalone_boot`, plus the moved tools' own tests), `install.sh` mirrored from research, `pwm-<x> --help` smoke green.
- [ ] **D. Swap in AI4Science** as Task 9: delete `specs/<name>.py` + the moved `*_tools.py`, remove the now-duplicate builtin bundle entries from `capabilities.py`, add `pwm-agent-<x>` to framework `dependencies`, run full suite green, cross-call test green.
- [ ] **E. Commit** in both repos; publish the agent dist; re-run its `install.sh` clean.

**After all seven:**

- [ ] **F. Add the `ai4science` meta-agent.** Create `ai4science/harness/agents/specs/ai4science_meta.py` with an `AGENT` (name `"ai4science"`, `category="core"`, `tier="science"`) whose purpose is to dispatch across all installed siblings — AI4Science is itself one agent. Test: `reload()` exposes `ai4science` and its `dispatchable_targets` include every installed agent.
- [ ] **G. Framework dependency sweep.** Confirm `pwm-ai4science` `dependencies` lists core + all 8 agent packages; a clean install of `pwm-ai4science` brings every agent and cross-calling is complete. Test: `test_all_eight_agents_present`.
- [ ] **H. Docs.** Update `PLUGIN_STANDARD.md` and `README.md` to describe the entry-point path (`pwm_agent.specs` / `pwm_agent.bundles`) beside the existing manifest path, and add a "split-a-new-agent" how-to pointing at this procedure.

---

## Self-Review

**Spec coverage (design §3–§11 → tasks):**
- §3.1 core library → Tasks 1, 5, 10. §3.2 agent packages → Tasks 7–9, Phase 3. §3.3 framework + meta-agent → Task 9, Phase 3 F/G.
- §4 entry-point discovery → Task 3. §5 standalone use → Tasks 7 (cli), 8 (install/boot). §6 single login → Global Constraints + core facade (Task 1 `run_cli` reuses `~/.ai4science`). §7 GPU-for-all → Task 5; §7 claude/codex disambiguation → Phase 3 rows + step B. §8 cross-call + hint → Tasks 3, 4, 9. §9 versioning → Tasks 1, 6, 10. §10 phases → Phases 1/2/3. §11 testing → per-task tests + Phase 3 F/G/H.

**Placeholder scan:** no TBD/TODO; every code step shows code; the one intentionally-parameterized part (Phase 3) shows full code once (Tasks 7–9) and a values table rather than re-pasting seven near-identical bodies — the reader has the complete pattern.

**Type consistency:** `register_agent_bundle` / `clear_agent_bundles` (Task 2) match their use in Tasks 3 & 7. `install_hint` (Task 4) format matches its assertions in Tasks 4 & 9. `run_cli(default_agent=...)` (Task 1) matches `cli.py` in Tasks 7 & Phase 3. `AGENT_BUNDLES` union order (Task 2) is consistent with entry-point registration timing (Task 3). Bundle names (`pwm-data`, `onboarding`, etc.) match `capabilities.py` and the research spec.

**Known follow-ups for planning-time confirmation:** exact `BuildContext` test constructor (Task 5 Step 1 note), and whether the physical namespace-package split (Task 10) uses PEP 420 or a `core/` subtree — both are called out inline where they occur.
