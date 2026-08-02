"""Where sarsi keeps everything — one resolver, shared by the registry, the
per-agent directories, the ledgers and the vault so they never disagree.

Deliberately **not** `machine.state.state_dir()`. That path is the machine
agent's control-plane store; sarsi couples to ai4science as a library, not as a
system, so it keeps its own root.

Precedence:
  1. `SARSI_STATE_DIR` (tests, and multi-profile installs).
  2. `~/.sarsi`.
  3. if home can't be resolved, a per-user temp dir keyed by username/uid —
     never a world-shared `/tmp/sarsi`, so one user's vault decisions and task
     records can't land in another's directory.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def state_dir() -> Path:
    env = os.environ.get("SARSI_STATE_DIR")
    if env:
        return Path(env)
    try:
        return Path.home() / ".sarsi"
    except Exception:
        return Path(tempfile.gettempdir()) / f"sarsi-{_user_tag()}"


def _user_tag() -> str:
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        try:
            return str(os.getuid())            # type: ignore[attr-defined]
        except Exception:
            return "user"
