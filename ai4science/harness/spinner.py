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
            self.stream.write(f"\r\x1b[2m{frame} {self.label}… ({secs}s)\x1b[0m")
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
