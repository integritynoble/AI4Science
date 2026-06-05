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
    # Dispatch tool is added in a later task (only when main). Left out here on purpose.
    return reg
