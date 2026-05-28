"""Image input — attach images to a chat turn as multimodal content blocks.

Claude Code lets you show the model a screenshot / plot / diagram. We
support the same via @-mention of an image file (e.g. ``@recon.png what's
wrong with this reconstruction?``). The image is base64-encoded into an
Anthropic-format ``image`` content block and sent as a structured user
message through the SDK's streaming input path.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Tuple

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Guard against accidentally base64-ing a huge file into the prompt.
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def media_type_for(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def encode_image(path: Path) -> Tuple[str, str]:
    """Return (media_type, base64_data) for an image file."""
    data = path.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"image too large ({len(data)} bytes > {MAX_IMAGE_BYTES})")
    return media_type_for(path), base64.b64encode(data).decode("ascii")


def build_user_message(text: str, image_paths: List[Path]) -> Dict[str, Any]:
    """Build an Anthropic-format user message mixing text + image blocks.

    Shape matches the SDK's streaming-input ``user`` event:
      {"type":"user","message":{"role":"user","content":[ ...blocks... ]}}
    """
    content: List[Dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    for p in image_paths:
        media_type, b64 = encode_image(p)
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })
    return {"type": "user", "message": {"role": "user", "content": content}}


async def single_message_stream(message: Dict[str, Any]):
    """Yield one structured message — streaming-input form of a single turn."""
    yield message
