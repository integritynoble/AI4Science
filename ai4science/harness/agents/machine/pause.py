"""Owner pause/resume signal for governed drives.

The interactive `session operate` loop yields automatically when you attach to
its tmux session. A headless `--guide` drive has no terminal to attach to, so the
owner pauses it explicitly: `singularity session pause`. While paused, the
governance hook holds every action (deny) and the guide loop waits between rounds
— `resume` lets it continue. Keyed per owner (a "pause my machine" switch), stored
as a flag file next to the other machine state. Fail-safe: reads never raise.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def _pause_dir() -> Path:
    from ai4science.harness.agents.machine.state import state_dir
    return state_dir() / "pwm-cc-pause"


def _owner() -> str:
    from ai4science.harness.agents.machine.trust import _owner as owner
    return owner()


def _flag(key: Optional[str] = None) -> Path:
    return _pause_dir() / (str(key) if key else _owner())


def is_paused(key: Optional[str] = None) -> bool:
    try:
        return _flag(key).exists()
    except Exception:
        return False


def pause(key: Optional[str] = None) -> bool:
    try:
        _pause_dir().mkdir(parents=True, exist_ok=True)
        _flag(key).write_text("paused")
        return True
    except Exception:
        return False


def resume(key: Optional[str] = None) -> bool:
    try:
        _flag(key).unlink()
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False
