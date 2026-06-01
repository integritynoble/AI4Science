from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CredInfo:
    kind: str                  # "openai_compat" | "anthropic"
    base_url: str
    api_key: Optional[str]
    model: Optional[str]


def resolve(backend: str) -> CredInfo:
    if backend == "anthropic":
        return CredInfo("anthropic", "https://api.anthropic.com/v1/messages",
                        os.environ.get("ANTHROPIC_API_KEY"), None)
    if backend == "gemini":
        from ai4science.llm import gemini
        base = gemini.resolve_base().rstrip("/") + "/chat/completions"
        return CredInfo("openai_compat", base, gemini.resolve_key(), None)
    from ai4science.llm import openai_compat as oc
    base = oc.resolve_base(backend).rstrip("/") + "/chat/completions"
    return CredInfo("openai_compat", base, oc.resolve_key(backend),
                    oc.default_model(backend))


def available(backend: str) -> bool:
    try:
        c = resolve(backend)
        return bool(c.api_key and c.base_url)
    except Exception:
        return False
