"""Plug-and-play agents & tools from manifest files — no code PR required.

A user drops a JSON or TOML manifest into the plugins dir
(`AI4SCIENCE_PLUGINS_DIR`, default `~/.ai4science/plugins/`). At
`registry.reload()` each manifest becomes either:

  - kind="agent"  → an AgentSpec added to the registry (dispatchable as a
                    sub-agent, like the built-ins), with its own wallet + price.
  - kind="tool"   → a dynamic capability bundle (its tool CODE is an external
                    MCP server) that any agent can reference in `capabilities`;
                    an optional `attach_to` list injects it into existing agents.

Tool code never runs in-process: it plugs in as an MCP server (stdio), built
lazily via `BuildContext.mcp_client_factory`. Manifests are pure data.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.tools.base import Tool

_VALID_TIERS = ("open", "science")
_VALID_KINDS = ("agent", "tool")


class ManifestError(ValueError):
    pass


def plugins_dir() -> Path:
    return Path(os.environ.get("AI4SCIENCE_PLUGINS_DIR")
                or (Path.home() / ".ai4science" / "plugins")).expanduser()


@dataclass(frozen=True)
class ToolPlugin:
    """A tool plug-in: a named capability bundle backed by MCP servers."""
    name: str
    mcp_servers: Tuple[Dict[str, Any], ...]
    attach_to: Tuple[str, ...]
    wallet: Optional[str]
    price_pwm: float

    def provider(self) -> Callable[[BuildContext], List[Tool]]:
        servers = self.mcp_servers

        def _build(ctx: BuildContext) -> List[Tool]:
            factory = getattr(ctx, "mcp_client_factory", None)
            if factory is None:
                return []  # no MCP factory wired → tool code unavailable (graceful)
            from ai4science.harness.mcp_client import mcp_tools
            out: List[Tool] = []
            for s in servers:
                try:
                    client = factory(s)
                    out.extend(mcp_tools(client))
                except Exception:
                    continue  # a broken server never breaks the whole registry
            return out

        return _build


def _str(data: dict, key: str, *, required: bool = False, default: str = "") -> str:
    v = data.get(key, default)
    if required and not (isinstance(v, str) and v.strip()):
        raise ManifestError(f"manifest missing required string field {key!r}")
    if v is not None and not isinstance(v, str):
        raise ManifestError(f"manifest field {key!r} must be a string")
    return v or default


def _tuple(data: dict, key: str) -> Tuple:
    v = data.get(key, [])
    if v in (None, ""):
        return ()
    if not isinstance(v, (list, tuple)):
        raise ManifestError(f"manifest field {key!r} must be a list")
    return tuple(v)


def parse_agent_manifest(data: dict) -> AgentSpec:
    name = _str(data, "name", required=True)
    tier = _str(data, "tier", default="science")
    if tier not in _VALID_TIERS:
        raise ManifestError(f"agent {name!r}: tier must be one of {_VALID_TIERS}")
    category = _str(data, "category", default="specific")
    price = float(data.get("price_pwm", 0.0) or 0.0)
    return AgentSpec(
        name=name,
        tier=tier,
        category=category,
        title=_str(data, "title", required=True),
        description=_str(data, "description", required=True),
        keywords=_tuple(data, "keywords"),
        system_prompt=(data.get("system_prompt") or None),
        capabilities=_tuple(data, "capabilities"),
        allow_as_subagent=bool(data.get("allow_as_subagent", True)),
        aliases=_tuple(data, "aliases"),
        default_backend=(data.get("default_backend") or None),
        order=int(data.get("order", 100)),
        wallet=(_str(data, "wallet") or None),
        price_pwm=price,
        mcp_servers=tuple(_tuple(data, "mcp_servers")),
        source="plugin",
    )


def parse_tool_manifest(data: dict) -> ToolPlugin:
    name = _str(data, "name", required=True)
    servers = tuple(_tuple(data, "mcp_servers"))
    return ToolPlugin(
        name=name,
        mcp_servers=servers,
        attach_to=tuple(str(a) for a in _tuple(data, "attach_to")),
        wallet=(_str(data, "wallet") or None),
        price_pwm=float(data.get("price_pwm", 0.0) or 0.0),
    )


def _load_manifest_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        import tomllib
        return tomllib.loads(text)
    return json.loads(text)


def parse_manifest(data: dict):
    """Return an AgentSpec (kind=agent) or a ToolPlugin (kind=tool)."""
    kind = _str(data, "kind", default="agent")
    if kind not in _VALID_KINDS:
        raise ManifestError(f"kind must be one of {_VALID_KINDS}, got {kind!r}")
    return parse_agent_manifest(data) if kind == "agent" else parse_tool_manifest(data)


def load_plugins(directory: Optional[Path] = None) -> Tuple[List[AgentSpec], List[ToolPlugin], List[str]]:
    """Scan the plugins dir. Returns (agent_specs, tool_plugins, errors).

    A malformed manifest is collected as an error string and skipped — one bad
    plug-in never blocks the rest (or the built-in agents)."""
    d = Path(directory) if directory else plugins_dir()
    agents: List[AgentSpec] = []
    tools: List[ToolPlugin] = []
    errors: List[str] = []
    if not d.exists():
        return agents, tools, errors
    for path in sorted(list(d.glob("*.json")) + list(d.glob("*.toml"))):
        try:
            obj = parse_manifest(_load_manifest_file(path))
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        (agents if isinstance(obj, AgentSpec) else tools).append(obj)
    return agents, tools, errors
