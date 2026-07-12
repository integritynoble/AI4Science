from __future__ import annotations
import json
import re

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)
_INLINE = re.compile(r'"solver"\s*:\s*"([^"]+)"')

def extract_solver_key(text: str, valid_keys) -> str | None:
    valid = set(valid_keys)
    text = text or ""
    for m in _FENCE.finditer(text):
        try:
            k = json.loads(m.group(1)).get("solver")
            if k in valid:
                return k
        except Exception:
            pass
    m = _INLINE.search(text)
    if m and m.group(1) in valid:
        return m.group(1)
    mentioned = [k for k in valid if re.search(rf"\b{re.escape(k)}\b", text)]
    if len(mentioned) == 1:
        return mentioned[0]
    return None
