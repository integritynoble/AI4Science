"""Global user-interrupt request (Esc / Ctrl-C in the TUI, like Claude Code).

One process-wide event: the UI thread sets it, long-running tools poll it
(shell.bash kills its process tree), and run_loop consumes it to end the turn
cleanly. It is a REQUEST flag, not a hard abort — tools that never poll it
still fall back to their own timeouts.

Cancellers make the interrupt INSTANT instead of merely cooperative. A
streaming adapter registers a callback (e.g. ``response.close``) while it is
blocked in a network read; request() fires every registered callback, which
closes the socket so the blocked read raises at once — the user no longer waits
for the next token before Ctrl-C takes effect. This is what makes interrupt
feel immediate on a slow founder-served backend.
"""
from __future__ import annotations

import threading
from typing import Callable, List

_EVENT = threading.Event()
_LOCK = threading.Lock()
_CANCELLERS: List[Callable[[], None]] = []


def request() -> None:
    """Ask the running turn to stop as soon as possible, and abort any in-flight
    network read so a blocked stream breaks immediately (not at the next token)."""
    _EVENT.set()
    with _LOCK:
        cbs = list(_CANCELLERS)
    for cb in cbs:                       # close sockets / cancel streams
        try:
            cb()
        except Exception:
            pass


def requested() -> bool:
    return _EVENT.is_set()


def clear() -> None:
    _EVENT.clear()


def register_canceller(fn: Callable[[], None]) -> None:
    """Register an abort callback (fired by request()). Adapters register their
    active response's ``close`` while streaming and unregister when done."""
    with _LOCK:
        _CANCELLERS.append(fn)


def unregister_canceller(fn: Callable[[], None]) -> None:
    with _LOCK:
        try:
            _CANCELLERS.remove(fn)
        except ValueError:
            pass
