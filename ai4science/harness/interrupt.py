"""Global user-interrupt request (Esc in the TUI, like Claude Code).

One process-wide event: the UI thread sets it, long-running tools poll it
(shell.bash kills its process tree), and run_loop consumes it to end the turn
cleanly. It is a REQUEST flag, not a hard abort — tools that never poll it
still fall back to their own timeouts.
"""
from __future__ import annotations

import threading

_EVENT = threading.Event()


def request() -> None:
    """Ask the running turn to stop as soon as possible."""
    _EVENT.set()


def requested() -> bool:
    return _EVENT.is_set()


def clear() -> None:
    _EVENT.clear()
