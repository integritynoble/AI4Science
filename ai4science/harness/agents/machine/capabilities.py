"""Cross-platform machine capability detection.

Read-only. `which`/`system`/`machine` are injectable so tests can simulate every
OS without those hosts. Detection never mutates anything and never runs a
consequential command.
"""
from __future__ import annotations

import os
import platform
import shutil
from typing import Callable, Dict

# tools the machine agent cares about when bootstrapping Claude Code
_PROBED_TOOLS = ("claude", "node", "npm", "podman", "git")

_OS_MAP = {"linux": "linux", "darwin": "macos", "windows": "windows"}


def _norm_arch(m: str) -> str:
    m = (m or "").lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return m


def detect_machine(*,
                   which: Callable[[str], object] = shutil.which,
                   system: Callable[[], str] = platform.system,
                   machine: Callable[[], str] = platform.machine) -> Dict:
    os_id = _OS_MAP.get((system() or "").lower(), (system() or "").lower())
    return {
        "os": os_id,
        "arch": _norm_arch(machine()),
        "shell": os.environ.get("SHELL", "") or os.environ.get("COMSPEC", ""),
        "installed": {t: bool(which(t)) for t in _PROBED_TOOLS},
        "supported": os_id in ("linux", "macos", "windows"),
    }
