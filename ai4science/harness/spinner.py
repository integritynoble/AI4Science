"""An animated status indicator — the "shining star" Claude Code shows while
it is thinking or a tool is running. A background thread pulses a star + a
short label + elapsed seconds on a single line; stop() clears it cleanly so
real output prints over a blank line.

Quiet by design: a no-op when stdout isn't a TTY (pipes/CI), so it never
pollutes captured output.
"""
from __future__ import annotations

import itertools
import sys
import threading
import time

# pulsing star frames (Claude-Code feel) + a braille fallback are equivalent;
# the star reads as "shining".
_FRAMES = ["✶", "✷", "✸", "✹", "✺", "✹", "✸", "✷"]

# Claude Code's working star is a coral orange (brand ~#d97757);
# 256-color 173 (#d7875f) is the closest widely-supported match.
STAR_COLOR = "\x1b[38;5;173m"
_RESET = "\x1b[0m"
_DIM = "\x1b[2m"


class Spinner:
    def __init__(self, label: str = "working", stream=None):
        self.label = label
        self.stream = stream or sys.stdout
        self._stop = threading.Event()
        self._thread = None
        self._t0 = 0.0
        self._enabled = bool(getattr(self.stream, "isatty", lambda: False)())

    def _run(self) -> None:
        for frame in itertools.cycle(_FRAMES):
            if self._stop.is_set():
                break
            secs = int(time.monotonic() - self._t0)
            # warm-orange star (like Claude Code), dim label/elapsed
            self.stream.write(f"\r{STAR_COLOR}{frame}{_RESET} "
                              f"{_DIM}{self.label}… ({secs}s){_RESET}")
            self.stream.flush()
            self._stop.wait(0.12)

    def start(self, label: str = None) -> "Spinner":
        if not self._enabled or (self._thread and self._thread.is_alive()):
            if label:
                self.label = label
            return self
        if label:
            self.label = label
        self._stop.clear()
        self._t0 = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if not self._enabled:
            return
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.3)
            self._thread = None
        # clear the spinner line so output prints cleanly
        self.stream.write("\r\x1b[2K")
        self.stream.flush()

    # context-manager sugar
    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()
