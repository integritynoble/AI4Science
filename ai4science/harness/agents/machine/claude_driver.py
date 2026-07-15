"""Governed Claude Code driver — the machine agent operates Claude Code to finish
a task, with every tool call adjudicated by the session-driver hook.

`drive_claude` (1) wires the PreToolUse governance hook into the project, (2) runs
Claude Code headless on the task, and (3) returns the result. Claude does the work;
safe actions run, consequential ones are gated (ask), forbidden ones deny + halt.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional


def ensure_governance_hook(project_dir, *, ceiling: str = "A1") -> Path:
    """Write a project .claude/settings.json wiring the PreToolUse governance hook.
    Uses THIS interpreter (so the hook resolves ai4science from the same env)."""
    d = Path(project_dir) / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    cmd = f"PWM_CEILING={ceiling} {sys.executable} -m ai4science.harness.agents.machine.hook"
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "*", "hooks": [{"type": "command", "command": cmd, "timeout": 60}]}]}}
    path = d / "settings.json"
    path.write_text(json.dumps(settings, indent=2))
    return path


def _default_run(claude_bin: str, task: str, project_dir: str, timeout: float) -> Dict[str, Any]:
    try:
        p = subprocess.run([claude_bin, "-p", task], cwd=project_dir, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "exit_code": p.returncode,
                "output": (p.stdout or "")[-4000:], "stderr": (p.stderr or "")[-500:]}
    except FileNotFoundError:
        return {"ok": False, "reason": "claude not installed — run: "
                                       "singularity machine \"install claude code\""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"claude timed out after {timeout}s"}
    except Exception as e:                       # never let it escape
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:120]}"}


def drive_claude(task: str, *, project_dir=".", ceiling: str = "A1",
                 claude_bin: str = "claude", timeout: float = 300.0,
                 ensure_hook: bool = True,
                 run: Optional[Callable[[str, str, str, float], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Have the machine agent drive Claude Code on `task`, governed. Wires the hook
    (unless ensure_hook=False), runs Claude headless in project_dir, returns the
    result. `run`/`claude_bin` injectable for tests."""
    project_dir = os.path.abspath(str(project_dir))
    if not task or not task.strip():
        return {"ok": False, "reason": "empty task"}
    if ensure_hook:
        try:
            ensure_governance_hook(project_dir, ceiling=ceiling)
        except Exception as e:
            return {"ok": False, "reason": f"could not wire governance hook: {type(e).__name__}"}
    runner = run or _default_run
    result = runner(claude_bin, task, project_dir, timeout)
    result.setdefault("governed", True)
    result.setdefault("ceiling", ceiling)
    return result
