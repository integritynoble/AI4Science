from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional

BASH_TIMEOUT_SECONDS = 300


def bash(workspace: Path, *, cmd: str, _sink: Optional[Callable[[str], None]] = None) -> str:
    """Run a shell command. If _sink is given, stream combined output to it live."""
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=str(workspace),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except Exception as exc:
        return f"(failed to start: {exc})"

    buf = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            buf.append(line)
            if _sink is not None:
                _sink(line)
        proc.wait(timeout=BASH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        buf.append(f"\n(timed out after {BASH_TIMEOUT_SECONDS}s)")
    out = "".join(buf)
    if proc.returncode not in (0, None):
        out += f"\n(exit code {proc.returncode})"
    return out
