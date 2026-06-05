from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Dict, List, Optional

from ai4science.harness.tools.base import Registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.capabilities import resolve_capability, CAPABILITY_BUNDLES

_SPECS_DIR = Path(__file__).parent / "specs"
AGENT_REGISTRY: Dict[str, AgentSpec] = {}


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
    # Dispatch tool is added in a later task (only when main). Left out here on purpose.
    return reg


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
