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
import re
from typing import Callable, Optional

from ai4science.harness.events import Message, TextDelta, Usage

# Thresholds for "substantial": either several tool calls or a long crunch.
RECAP_MIN_TOOLS = 2
RECAP_MIN_SECONDS = 20.0

_SYSTEM = (
    "You write one-sentence end-of-turn recaps for a coding/research "
    "assistant. Say what the assistant DID, not what it concluded, in at most "
    "30 words, plain text, no markdown, no preamble.\n"
    "Never state a result, number or verdict as settled. If you mention a "
    "figure at all, carry the condition attached to it in the same breath — "
    "'0.0 once recomputed in float64', never a bare '0.0'. Dropping the "
    "condition and keeping the number is the one mistake that matters here: "
    "the recap is the sentence most people read, and a qualified finding "
    "reported flat becomes a false one."
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
    return vet("".join(parts).strip(), final_text=final_text)


#: A digit-bearing token that is a measurement rather than a coordinate. Paths,
#: line numbers, versions and shapes are how a recap says WHERE it looked, and
#: throwing those away would leave only the vaguest recaps standing.
_NOT_A_MEASUREMENT = re.compile(
    r"""(?x)
      \b\w+\.\w+:\d+          # coded.py:118
    | \b\w*\d+\w*\.(py|md|txt|json|csv|log|yaml|yml|toml|sh)\b
    | \b(float|int|uint|complex)\d+\b
    | \b\d+(x\d+)+\b           # 8x8x4
    | \bv\d+(\.\d+)*\b        # v2, v1.1.7 — the `v` is what makes it a version
    | \b\d+(\.\d+){2,}\b      # 1.1.7 — three parts. TWO is a number: `0.0` was
                              # being exempted as a version, which let through
                              # exactly the recap this function exists to catch.
    | \b[A-Za-z]+-?\d+\b        # A1, tsk_…, GPT-4
    """)

_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def vet(text: Optional[str], *, final_text: str) -> Optional[str]:
    """Drop a recap that states a number the answer never did.

    Cheap, mechanical, and aimed at the worst case: a figure the recap model
    produced rather than read. A recap is decoration — the module says so — and
    dropping one costs nothing, while printing an invented measurement costs the
    reader the only thing the recap was for.

    Coordinates are not measurements. `coded.py:118`, `float64`, `8x8x4` and
    `A1` are how a recap says where it looked, so they are exempt; what has to
    appear in the answer is a bare quantity.
    """
    if not text:
        return None
    claimed = set(_NUMBER.findall(_NOT_A_MEASUREMENT.sub(" ", text)))
    if not claimed:
        return text
    present = set(_NUMBER.findall(final_text or ""))
    unsupported = {n for n in claimed if n not in present
                   and not any(n in p for p in present)}
    return None if unsupported else text
