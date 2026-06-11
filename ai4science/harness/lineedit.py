"""Readline line-editing for the REPLs — arrow keys + command history.

Plain input() on a Unix terminal does not interpret arrow keys: ↑/↓ for
previous/next command and ←/→ for cursor movement emit raw escape codes
(`^[[A` …). Importing `readline` makes input() interpret them and recall
history. This module enables it once, with a persisted per-mode history file,
and is a safe no-op where readline is unavailable (e.g. Windows without
pyreadline3 — the native console host already provides editing there).
"""
from __future__ import annotations

import os
from pathlib import Path

_DONE: set = set()


def enable(history_name: str = "repl") -> None:
    """Turn on arrow-key editing + persisted history for input(). Idempotent."""
    if history_name in _DONE:
        return
    _DONE.add(history_name)
    try:
        import atexit
        import readline
    except Exception:
        return                      # no readline (Windows stdlib) → console host edits
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ai4science"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = None
    hist = (base / f"history_{history_name}") if base else None
    if hist:
        try:
            readline.read_history_file(hist)
        except (OSError, Exception):
            pass
    try:
        readline.set_history_length(2000)
        readline.parse_and_bind("tab: complete")   # harmless; no completer set
    except Exception:
        pass
    if hist:
        atexit.register(lambda: _save(readline, hist))


def _save(readline, hist) -> None:
    try:
        readline.write_history_file(hist)
    except Exception:
        pass
