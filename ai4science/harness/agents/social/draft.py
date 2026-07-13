"""Deterministic draft generation for the social-media agent.

``draft_post`` turns a Mastodon home-timeline payload (a list of status
dicts, as returned by the ``/api/v1/timelines/home`` API) into a short,
human-readable, and fully deterministic summary string. No randomness,
no wall-clock, no network — same input always yields the same output.
"""

from __future__ import annotations


def _top_author(timeline: list[dict]) -> str | None:
    """Return the acct of the most frequently posting author.

    Ties are broken deterministically by first appearance in the
    timeline (stable behaviour, no dependence on dict ordering quirks
    beyond Python's guaranteed insertion order).
    """
    counts: dict[str, int] = {}
    order: list[str] = []
    for item in timeline:
        acct = (item.get("account") or {}).get("acct") or "unknown"
        if acct not in counts:
            counts[acct] = 0
            order.append(acct)
        counts[acct] += 1

    best = None
    best_count = -1
    for acct in order:
        if counts[acct] > best_count:
            best = acct
            best_count = counts[acct]
    return best


def draft_post(timeline: list[dict]) -> str:
    """Build a deterministic templated summary of a home timeline.

    Args:
        timeline: list of status dicts (as returned by Mastodon's
            ``/api/v1/timelines/home`` endpoint). May be empty.

    Returns:
        A non-empty, deterministic summary string.
    """
    n = len(timeline)
    if n == 0:
        return "Read 0 timeline items. No new posts to summarize."

    top_author = _top_author(timeline)
    return f"Read {n} timeline items. Top author: {top_author}."
