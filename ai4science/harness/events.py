from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]   # JSON Schema object


@dataclass
class ImagePart:
    media_type: str          # e.g. "image/png"
    data_b64: str            # base64-encoded image bytes


@dataclass
class Message:
    role: str                                  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: List["ToolCall"] = field(default_factory=list)  # assistant tool requests
    tool_call_id: Optional[str] = None         # set on role="tool" result messages
    images: List["ImagePart"] = field(default_factory=list)


# ---- stream events (adapter -> loop) ----
@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]
    # Opaque per-provider passthrough that must be echoed back on the next request
    # (e.g. Gemini's OpenAI-compat `extra_content.google.thought_signature`).
    extra: Optional[Dict[str, Any]] = None


@dataclass
class Usage:
    input: Optional[int] = None
    output: Optional[int] = None
    total: Optional[int] = None


@dataclass
class Done:
    stop_reason: Optional[str] = None


def load_image(path) -> "ImagePart":
    import base64
    import mimetypes
    from pathlib import Path
    p = Path(path)
    data = p.read_bytes()
    media_type = mimetypes.guess_type(str(p))[0] or "image/png"
    return ImagePart(media_type=media_type, data_b64=base64.b64encode(data).decode("ascii"))
