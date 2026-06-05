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
