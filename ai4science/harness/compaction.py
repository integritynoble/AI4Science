"""Context compaction — keep a long session inside the model's window.

When the transcript grows past `limit_chars`, the older part is replaced by
one summary message. Three things this must never do:

  * split an assistant message that carries tool calls from the tool results
    that answer it — the request after that is invalid on every provider;
  * lose the leading system prompt(s) — the mode grounding is not "earlier
    conversation", it is the contract the session runs under;
  * let a summarizer failure take the history with it — a summary is a
    convenience, the transcript is the record. If summarizing raises, the
    history is returned unchanged and the caller may try again next turn.
"""
from __future__ import annotations

from typing import Callable, List, Tuple

from ai4science.harness.events import Message


def _size(history: List[Message]) -> int:
    return sum(len(m.content or "") for m in history)


COMPACTED_MARK = "[compacted earlier conversation]"


def _leading_system(history: List[Message]) -> int:
    """How many leading system messages are the session's own prompts. An
    earlier compaction summary is a system message too, but it belongs to the
    head — it is re-summarized, never accumulated, so repeated compaction keeps
    exactly one summary."""
    n = 0
    while (n < len(history) and history[n].role == "system"
           and not (history[n].content or "").startswith(COMPACTED_MARK)):
        n += 1
    return n


def _align_cut(history: List[Message], cut: int, floor: int) -> int:
    """Move `cut` back to the nearest index that starts a user turn, so the
    tail never begins with a tool result or a continuation of a tool-using
    exchange. Falls back to `floor` (right after the system prompts) when no
    user message exists in range."""
    i = cut
    while i > floor and history[i].role != "user":
        i -= 1
    return i if history[i].role == "user" else floor


def maybe_compact(history: List[Message], *, limit_chars: int, keep_recent: int = 6,
                  summarize: Callable[[str], str]) -> Tuple[List[Message], bool]:
    """If history exceeds limit_chars, replace the older prefix with one summary
    system message, preserving the leading system prompts and the last
    `keep_recent` messages (extended back to a user-turn boundary).
    Returns (history, compacted?)."""
    if limit_chars <= 0 or _size(history) <= limit_chars:
        return history, False
    floor = _leading_system(history)
    if len(history) - floor <= keep_recent + 1:
        return history, False
    cut = _align_cut(history, len(history) - keep_recent, floor)
    if cut <= floor:
        return history, False           # nothing summarizable before the tail
    prefix, head, tail = history[:floor], history[floor:cut], history[cut:]
    transcript = "\n".join(f"{m.role}: {m.content}" for m in head if m.content)
    try:
        summary = summarize(transcript)
    except Exception:
        return history, False
    if not (summary or "").strip():
        return history, False
    compacted = prefix + [Message(role="system",
                                  content=f"{COMPACTED_MARK}\n{summary}")] + tail
    return compacted, True
