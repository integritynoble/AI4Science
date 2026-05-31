from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]     # JSON Schema
    func: Callable[..., str]       # func(workspace: Path, **args) -> str
    mutating: bool = False         # True => must pass the permission gate
    streams: bool = False          # True => func accepts _sink kwarg for live output


class Registry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def names(self):
        return list(self._tools.keys())

    def specs(self):
        from ai4science.harness.events import ToolSpec
        return [ToolSpec(t.name, t.description, t.parameters) for t in self._tools.values()]
