from __future__ import annotations

import json
from typing import Any, Dict


def loads_lenient(s: str) -> Dict[str, Any]:
    """Parse a streamed tool-call argument string into a dict, robustly.

    Some providers (notably Gemini's OpenAI-compat stream) occasionally emit a
    malformed or doubled arguments payload, e.g. two concatenated JSON objects,
    which makes a plain ``json.loads`` raise ``JSONDecodeError: Extra data`` and
    crash the whole turn. We salvage the first valid JSON object via
    ``raw_decode`` rather than failing, and fall back to ``{}`` so the tool call
    still fires (an empty-args call is far better than a dead turn).
    """
    s = (s or "").strip()
    if not s:
        return {}
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        try:
            obj, _ = json.JSONDecoder().raw_decode(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
