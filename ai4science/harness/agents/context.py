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
    #: Directories outside the workspace this session may WRITE, declared by
    #: the caller (for sarsi, the plan's working directory). They reach the
    #: tool DESCRIPTIONS from here: a capability the model cannot discover
    #: changes nothing, which a live run demonstrated by reaching for a
    #: heredoc into a directory `write` had just been given.
    writable_roots: Optional[List[Path]] = None
    enable_mcp: bool = True
    mcp_clients: Optional[List[object]] = None
    # Builds an MCP client from a spec's mcp_servers entry: server_dict -> client
    # (the client exposes .server + list_tools/call_tool, like harness.mcp_client).
    # Injectable so tests can supply a fake; None disables per-agent MCP servers.
    mcp_client_factory: Optional[Callable[[dict], object]] = None
