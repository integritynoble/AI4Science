"""End-of-turn recap — Claude Code parity.

The product prints a one-sentence recap after substantial turns ("recap: You
asked …"). We mirror it with one cheap low-reasoning LLM call on the session's
current brand, only when the turn was worth recapping (several tools or a long
crunch). `AI4SCIENCE_RECAP` tunes it: `0`/`off`/`false` = never,
`always`/`1`/`on` = every turn, unset = substantial turns only. Failures are
silent — a recap is decoration, never worth breaking a turn over.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from ai4science.harness.events import Message, TextDelta, Usage

# Thresholds for "substantial": either several tool calls or a long crunch.
RECAP_MIN_TOOLS = 2
RECAP_MIN_SECONDS = 20.0

_SYSTEM = (
    "You write one-sentence end-of-turn recaps for a coding/research "
    "assistant. Summarize what the user asked and what the assistant "
    "found/did, in at most 30 words, plain text, no markdown, no preamble."
)


def should_recap(*, seconds: float, tools: int) -> bool:
    v = str(os.environ.get("AI4SCIENCE_RECAP", "")).strip().lower()
    if v in ("0", "off", "false", "no"):
        return False
    if v in ("1", "on", "always", "yes"):
        return True
    return tools >= RECAP_MIN_TOOLS or seconds >= RECAP_MIN_SECONDS


def generate_recap(adapter, model: str, *, user_text: str, final_text: str,
                   meter: Optional[Callable[[Usage], None]] = None) -> Optional[str]:
    """One-sentence recap via the current adapter. Returns None when empty."""
    history = [
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=(
            f"User asked: {user_text[:500]}\n\n"
            f"Assistant's answer (tail): {final_text[-800:]}\n\n"
            f"One-sentence recap:")),
    ]
    parts: list[str] = []
    for ev in adapter.stream(history, [], model=model, reasoning="low"):
        if isinstance(ev, TextDelta):
            parts.append(ev.text)
        elif isinstance(ev, Usage) and meter is not None:
            meter(ev)
    text = "".join(parts).strip()
    return text or None
