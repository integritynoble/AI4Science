from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

BASH_TIMEOUT_SECONDS = 300


def _kill_tree(proc: "subprocess.Popen") -> None:
    """Kill the whole process group (shell + its children), falling back to a
    plain kill. Closing stdout unblocks the reader's blocked readline at once."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        if proc.stdout is not None:
            proc.stdout.close()
    except Exception:
        pass


def bash(workspace: Path, *, cmd: str, _sink: Optional[Callable[[str], None]] = None) -> str:
    """Run a shell command. Streams combined output to _sink live (if given) while
    enforcing a hard wall-clock timeout via a reader thread + proc.wait(timeout).
    On timeout the whole process group is killed (so the command does not leak)."""
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=str(workspace),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            start_new_session=True,   # own process group → we can kill the whole tree
        )
    except Exception as exc:
        return f"(failed to start: {exc})"

    buf: List[str] = []

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                buf.append(line)
                if _sink is not None:
                    _sink(line)
        except Exception:
            pass

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    # Wait in short slices so a user interrupt (Esc in the TUI) kills the
    # command within ~200ms instead of blocking until the wall timeout.
    from ai4science.harness import interrupt
    deadline = time.monotonic() + BASH_TIMEOUT_SECONDS
    while True:
        try:
            proc.wait(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            if interrupt.requested():
                _kill_tree(proc)
                buf.append("\n(interrupted by user)")
                break
            if time.monotonic() >= deadline:
                _kill_tree(proc)
                buf.append(f"\n(timed out after {BASH_TIMEOUT_SECONDS}s)")
                break
    reader.join(timeout=5)

    out = "".join(buf)
    if proc.returncode not in (0, None):
        out += f"\n(exit code {proc.returncode})"
    return out
