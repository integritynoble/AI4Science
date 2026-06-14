from __future__ import annotations

from dataclasses import dataclass
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
    # Builds an MCP client from a spec's mcp_servers entry: server_dict -> client
    # (the client exposes .server + list_tools/call_tool, like harness.mcp_client).
    # Injectable so tests can supply a fake; None disables per-agent MCP servers.
    mcp_client_factory: Optional[Callable[[dict], object]] = None
