"""Where the machine agent keeps its per-session state — one resolver, shared by
the supervisor records, the trust ledger, and the hook's tripwire flags so they
never disagree.

Precedence:
  1. `PWM_CP_STATE_DIR` (set by the control plane in real deployments).
  2. a **per-user** path: `~/.local/share/pwm-cp` (matches the control-plane
     state location).
  3. if home can't be resolved, a per-user temp dir keyed by username/uid — never
     a world-shared `/tmp` path, so one user's flags can't leak into another's.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def state_dir() -> Path:
    env = os.environ.get("PWM_CP_STATE_DIR")
    if env:
        return Path(env)
    try:
        return Path.home() / ".local" / "share" / "pwm-cp"
    except Exception:
        return Path(tempfile.gettempdir()) / f"pwm-cp-{_user_tag()}"


def _user_tag() -> str:
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        try:
            return str(os.getuid())            # type: ignore[attr-defined]
        except Exception:
            return "user"
