from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

BASH_TIMEOUT_SECONDS = 300


def bash(workspace: Path, *, cmd: str, _sink: Optional[Callable[[str], None]] = None) -> str:
    """Run a shell command. Streams combined output to _sink live (if given) while
    enforcing a hard wall-clock timeout via a reader thread + proc.wait(timeout)."""
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=str(workspace),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
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
    try:
        proc.wait(timeout=BASH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        buf.append(f"\n(timed out after {BASH_TIMEOUT_SECONDS}s)")
    reader.join(timeout=5)

    out = "".join(buf)
    if proc.returncode not in (0, None):
        out += f"\n(exit code {proc.returncode})"
    return out
