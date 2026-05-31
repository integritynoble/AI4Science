from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]   # JSON Schema object


@dataclass
class Message:
    role: str                                  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: List["ToolCall"] = field(default_factory=list)  # assistant tool requests
    tool_call_id: Optional[str] = None         # set on role="tool" result messages


# ---- stream events (adapter -> loop) ----
@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Usage:
    input: Optional[int] = None
    output: Optional[int] = None
    total: Optional[int] = None


@dataclass
class Done:
    stop_reason: Optional[str] = None
