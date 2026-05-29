"""Gemini connectivity via the comparegpt key (OpenAI-compatible endpoint).

The key is read at runtime — never stored in the repo. Resolution order:
  1. AI4SCIENCE_GEMINI_API_KEY env var
  2. GEMINI_API_KEY in the comparegpt .env
     (path via AI4SCIENCE_COMPAREGPT_ENV, default below)

Uses Google's public OpenAI-compatible endpoint, so no Vertex/GCP service
account is needed — just the AI-Studio key.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_COMPAREGPT_ENV = "/home/spiritai/comparegpt-product/qa/.env"
DEFAULT_MODEL = "gemini-2.5-flash"


def _read_env_val(path: str, name: str) -> Optional[str]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(rf'^{re.escape(name)}\s*=\s*"?([^"\n]+)"?', text, re.M)
    return m.group(1).strip() if m else None


def _comparegpt_env() -> str:
    return os.environ.get("AI4SCIENCE_COMPAREGPT_ENV", DEFAULT_COMPAREGPT_ENV)


def resolve_key() -> Optional[str]:
    return (os.environ.get("AI4SCIENCE_GEMINI_API_KEY")
            or _read_env_val(_comparegpt_env(), "GEMINI_API_KEY"))


def resolve_base() -> str:
    return (os.environ.get("AI4SCIENCE_GEMINI_API_BASE")
            or _read_env_val(_comparegpt_env(), "GEMINI_API_BASE")
            or DEFAULT_BASE)


def is_available() -> bool:
    return bool(resolve_key())


def chat(messages: List[Dict[str, str]], model: str = DEFAULT_MODEL,
         timeout: int = 120) -> Tuple[str, Dict]:
    """Send a chat completion to Gemini's OpenAI-compatible endpoint.

    Returns (text, usage_dict). Raises RuntimeError if no key, or on HTTP error.
    """
    key = resolve_key()
    if not key:
        raise RuntimeError("no Gemini key (set AI4SCIENCE_GEMINI_API_KEY or "
                           "ensure the comparegpt .env has GEMINI_API_KEY)")
    req = urllib.request.Request(
        resolve_base().rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "messages": messages}).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        r = json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")
    return r["choices"][0]["message"]["content"], r.get("usage", {})
