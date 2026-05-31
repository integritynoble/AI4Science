from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from ai4science.harness.events import ImagePart, load_image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MENTION = re.compile(r"@([^\s@]+)")
_MAX_INLINE_CHARS = 50_000


def expand(line: str, workspace: Path) -> Tuple[str, List[ImagePart]]:
    """Expand @<path> tokens: inline text files, attach image files as ImageParts.
    Non-file @tokens are left untouched. Returns (rewritten_text, images)."""
    images: List[ImagePart] = []

    def _sub(m: "re.Match") -> str:
        token = m.group(1)
        p = (workspace / token)
        if not p.is_file():
            return m.group(0)
        if p.suffix.lower() in IMAGE_SUFFIXES:
            try:
                images.append(load_image(p))
            except Exception:
                return m.group(0)
            return f"[image: {token}]"
        try:
            content = p.read_text()[:_MAX_INLINE_CHARS]
        except Exception:
            return m.group(0)
        return f"\n\n--- {token} ---\n{content}\n--- end {token} ---\n"

    return _MENTION.sub(_sub, line), images
