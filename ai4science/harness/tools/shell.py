from __future__ import annotations

import subprocess
from pathlib import Path

BASH_TIMEOUT_SECONDS = 300


def bash(workspace: Path, *, cmd: str) -> str:
    try:
        p = subprocess.run(cmd, shell=True, cwd=str(workspace),
                           capture_output=True, text=True, timeout=BASH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return f"(timed out after {BASH_TIMEOUT_SECONDS}s)"
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        out += f"\n(exit code {p.returncode})"
    return out
