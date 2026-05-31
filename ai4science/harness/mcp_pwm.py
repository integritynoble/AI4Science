from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, List

from ai4science.harness.tools.base import Tool
from ai4science.agents import mcp_pwm as _pwm   # the deterministic coroutines

_STR = {"type": "string"}

# (name, description, extra-properties). workspace is injected automatically.
_SPECS = [
    ("pwm_status", "Workspace status: artifacts present + reports.", {}),
    ("pwm_validate", "Run ai4science validate on the workspace.", {}),
    ("pwm_judge_cassi", "Run the deterministic CASSI Physics Judge.", {}),
    ("pwm_lookup_artifact", "Read a PWM artifact by canonical name.", {"artifact": _STR}),
]


def _extract(result) -> str:
    """PWM coroutines return {"content": [{"type":"text","text":...}]}; join the text."""
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        return "".join(b.get("text", "") for b in result["content"]
                       if isinstance(b, dict) and b.get("type") == "text")
    return json.dumps(result, indent=2, default=str)


def _wrap(name: str) -> Callable[..., str]:
    def _tool(workspace: Path, **args) -> str:
        coro = getattr(_pwm, name)               # resolve at call time (monkeypatch-friendly)
        call_args = dict(args)
        call_args.setdefault("workspace", str(workspace))
        try:
            result = asyncio.run(coro(call_args))
        except Exception as exc:
            return f"[{name}] error: {exc}"
        return _extract(result)
    return _tool


def pwm_tools() -> List[Tool]:
    out = []
    for name, desc, extra in _SPECS:
        props = {"workspace": _STR, **extra}
        out.append(Tool(name, desc, {"type": "object", "properties": props},
                        _wrap(name), mutating=False))
    return out
