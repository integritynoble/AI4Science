from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Dict, List, Optional

import dataclasses

from ai4science.harness.tools.base import Registry, Tool
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.capabilities import (
    resolve_capability, CAPABILITY_BUNDLES,
    register_plugin_bundle, clear_plugin_bundles,
    register_agent_bundle, clear_agent_bundles,   # NEW
)

_SPECS_DIR = Path(__file__).parent / "specs"
AGENT_REGISTRY: Dict[str, AgentSpec] = {}
# Non-fatal problems from the last reload (bad manifests, etc.) — surfaced by /mcp diag.
PLUGIN_ERRORS: List[str] = []


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


def _attach_spec_mcp_servers(spec: AgentSpec, ctx: BuildContext, reg: Registry) -> None:
    """A plug-in agent's own tool code: build a client per declared MCP server and
    merge its namespaced tools. Needs ctx.mcp_client_factory; no-op otherwise."""
    servers = getattr(spec, "mcp_servers", ()) or ()
    factory = getattr(ctx, "mcp_client_factory", None)
    if not servers or factory is None:
        return
    from ai4science.harness.mcp_client import mcp_tools
    for s in servers:
        try:
            client = factory(s)
            for t in mcp_tools(client):
                reg.add(t)
        except Exception:
            continue  # a broken plug-in server never breaks the registry


def build_registry_for(spec: AgentSpec, *, is_subagent: bool, ctx: BuildContext) -> Registry:
    reg = _claude_code_base(ctx)
    for cap in spec.capabilities:
        for t in resolve_capability(cap, ctx):
            reg.add(t)
    _attach_spec_mcp_servers(spec, ctx, reg)
    if spec.extra_tools:
        for t in spec.extra_tools(ctx):
            reg.add(t)
    if not is_subagent:
        tool = _agent_dispatch_tool(spec, ctx)
        if tool is not None:
            reg.add(tool)
    return reg


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
        child_spec = AGENT_REGISTRY.get(subagent_type)
        if subagent_type not in targets or child_spec is None:
            return (f"[task] unknown subagent_type {subagent_type!r}; "
                    f"available: {listed}")
        session = ctx.session_factory(spec=child_spec, ctx=ctx)
        sys = child_spec.system_prompt or ""
        return session.run_turn(f"{sys}\n\nTASK: {prompt}" if sys else prompt)

    return Tool(
        name="task",
        description=("Delegate a focused sub-task to a fresh sub-agent. "
                     f"subagent_type one of: {listed}."),
        parameters={"type": "object",
                    "properties": {"subagent_type": {"type": "string", "enum": targets},
                                   "prompt": {"type": "string"}},
                    "required": ["subagent_type", "prompt"]},
        func=_task, mutating=False,
    )


def _load_spec_file(path: Path) -> AgentSpec:
    spec = importlib.util.spec_from_file_location(f"_agentspec_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    agent = getattr(module, "AGENT", None)
    if not isinstance(agent, AgentSpec):
        raise ValueError(f"{path} has no top-level AGENT: AgentSpec")
    return agent


# Alias → canonical name (e.g. the old "common" → "unified-LLM"). Rebuilt by reload().
AGENT_ALIASES: Dict[str, str] = {}


def _iter_entry_points(*, group: str):
    """Indirection so tests can inject fake entry points."""
    from importlib.metadata import entry_points
    try:
        return list(entry_points(group=group))       # py3.10+ selectable API
    except TypeError:                                 # very old importlib shim
        return list(entry_points().get(group, []))


def _validate_caps(name: str, caps, where: str) -> None:
    for cap in caps:
        if cap not in CAPABILITY_BUNDLES:
            valid = ", ".join(sorted(CAPABILITY_BUNDLES))
            raise ValueError(
                f"agent {name!r} ({where}) uses unknown capability "
                f"{cap!r}; valid: {valid}")


def reload(specs_dir: Optional[Path] = None, *, load_plugins: bool = True) -> Dict[str, AgentSpec]:
    """Discover built-in specs/*.py (each exposing AGENT), then merge manifest
    plug-ins from the plugins dir, into AGENT_REGISTRY."""
    directory = Path(specs_dir) if specs_dir else _SPECS_DIR
    found: Dict[str, AgentSpec] = {}
    aliases: Dict[str, str] = {}
    clear_plugin_bundles()
    PLUGIN_ERRORS.clear()
    for path in sorted(directory.glob("*.py")):
        if path.name == "__init__.py":
            continue
        agent = _load_spec_file(path)
        if agent.name in found:
            raise ValueError(f"duplicate agent name {agent.name!r} ({path})")
        _validate_caps(agent.name, agent.capabilities, str(path))
        found[agent.name] = agent
        for alias in agent.aliases:
            aliases[alias] = agent.name

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

    # ── manifest plug-ins (tools register bundles first, so agent plug-ins and
    #    attach_to can reference them) ──
    extra_caps: Dict[str, List[str]] = {}   # agent name -> bundles to inject (attach_to)
    if load_plugins:
        from ai4science.harness.agents import plugins as _plugins
        plug_agents, plug_tools, errors = _plugins.load_plugins()
        PLUGIN_ERRORS.extend(errors)
        for tp in plug_tools:
            if tp.name in CAPABILITY_BUNDLES:
                PLUGIN_ERRORS.append(f"tool plug-in {tp.name!r}: name collides with an "
                                     "existing bundle; skipped")
                continue
            register_plugin_bundle(tp.name, tp.provider())
            for target in tp.attach_to:
                extra_caps.setdefault(target, []).append(tp.name)
        for agent in plug_agents:
            if agent.name in found:
                PLUGIN_ERRORS.append(f"agent plug-in {agent.name!r}: name collides with a "
                                     "built-in agent; skipped")
                continue
            try:
                _validate_caps(agent.name, agent.capabilities, "plugin")
            except ValueError as exc:
                PLUGIN_ERRORS.append(str(exc))
                continue
            found[agent.name] = agent
            for alias in agent.aliases:
                aliases[alias] = agent.name

    # attach_to: add each tool plug-in's bundle to the named agents (frozen specs
    # → replace with a copy whose capabilities include the bundle, de-duped).
    for target, bundles in extra_caps.items():
        spec = found.get(target)
        if spec is None:
            PLUGIN_ERRORS.append(f"attach_to target {target!r} is not a known agent; skipped")
            continue
        merged = tuple(dict.fromkeys(spec.capabilities + tuple(bundles)))
        found[target] = dataclasses.replace(spec, capabilities=merged)

    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(found)
    AGENT_ALIASES.clear()
    AGENT_ALIASES.update(aliases)
    return AGENT_REGISTRY


def get(name: str) -> Optional[AgentSpec]:
    """Resolve a mode by exact name, then alias, then case-insensitively.

    Case-insensitive so a caller that lower-cases input (e.g. the CLI) still
    resolves a mixed-case id like 'unified-LLM', and so 'common' →
    'unified-LLM' via the alias regardless of casing.
    """
    if not name:
        return None
    spec = AGENT_REGISTRY.get(name)
    if spec is not None:
        return spec
    canonical = AGENT_ALIASES.get(name)
    if canonical:
        return AGENT_REGISTRY.get(canonical)
    low = name.lower()
    for n, s in AGENT_REGISTRY.items():
        if n.lower() == low:
            return s
    for alias, n in AGENT_ALIASES.items():
        if alias.lower() == low:
            return AGENT_REGISTRY.get(n)
    return None


def core_agents() -> List[AgentSpec]:
    return sorted((s for s in AGENT_REGISTRY.values() if s.category == "core"),
                  key=lambda s: (s.order, s.name))


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
