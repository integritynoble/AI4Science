from __future__ import annotations

from typing import Callable, List, Tuple

from ai4science.harness.events import Message


def _size(history: List[Message]) -> int:
    return sum(len(m.content or "") for m in history)


def maybe_compact(history: List[Message], *, limit_chars: int, keep_recent: int = 6,
                  summarize: Callable[[str], str]) -> Tuple[List[Message], bool]:
    """If history exceeds limit_chars, replace the older prefix with one summary
    system message, preserving the last `keep_recent` messages. Returns (history, compacted?)."""
    if _size(history) <= limit_chars or len(history) <= keep_recent + 1:
        return history, False
    head = history[:-keep_recent]
    tail = history[-keep_recent:]
    transcript = "\n".join(f"{m.role}: {m.content}" for m in head if m.content)
    summary = summarize(transcript)
    compacted = [Message(role="system", content=f"[compacted earlier conversation]\n{summary}")] + tail
    return compacted, True
