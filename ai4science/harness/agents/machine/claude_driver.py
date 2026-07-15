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


def _default_run(claude_bin: str, task: str, project_dir: str, timeout: float,
                 *, name: Optional[str] = None, ceiling: str = "A1") -> Dict[str, Any]:
    """Launch Claude Code headless, registering a durable supervisor record for the
    child process while it runs (so `session ls` shows the driven session), and
    releasing it on exit."""
    from ai4science.harness.agents.machine import supervisor as _sup
    try:
        proc = subprocess.Popen([claude_bin, "-p", task], cwd=project_dir,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        return {"ok": False, "reason": "claude not installed — run: "
                                       "singularity machine \"install claude code\""}
    except Exception as e:                       # never let it escape
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:120]}"}
    rec = None
    try:
        rec = _sup.create(pid=proc.pid, cwd=project_dir, name=name, ceiling=ceiling)
    except Exception:
        rec = None
    try:
        out, err = proc.communicate(timeout=timeout)
        result = {"ok": proc.returncode == 0, "exit_code": proc.returncode,
                  "output": (out or "")[-4000:], "stderr": (err or "")[-500:]}
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        result = {"ok": False, "reason": f"claude timed out after {timeout}s"}
    except Exception as e:
        result = {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:120]}"}
    finally:
        if rec is not None:
            try:
                _sup.close(rec["name"])           # session ended → release the record
            except Exception:
                pass
    if rec is not None:
        result.setdefault("name", rec["name"])
    return result


def approval_mode() -> str:
    """How consequential actions get approved during a drive:
    'telegram' when PWM_TELEGRAM_* is configured (Approve/Deny on the owner's
    phone — tasks finish after a tap), else 'local' (terminal prompt, or a
    fail-safe block when unattended)."""
    try:
        from ai4science.harness.agents.machine.telegram import telegram_config
        return "telegram" if telegram_config() else "local"
    except Exception:
        return "local"


def drive_claude(task: str, *, project_dir=".", ceiling: str = "A1", name: Optional[str] = None,
                 claude_bin: str = "claude", timeout: float = 300.0,
                 ensure_hook: bool = True,
                 run: Optional[Callable[[str, str, str, float], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Have the machine agent drive Claude Code on `task`, governed. Wires the hook
    (unless ensure_hook=False), runs Claude headless in project_dir, returns the
    result. Consequential actions are approved via Telegram by default when
    PWM_TELEGRAM_* is set (the hook + Claude inherit this process's env), so a task
    finishes after your tap. `run`/`claude_bin` injectable for tests."""
    project_dir = os.path.abspath(str(project_dir))
    if not task or not task.strip():
        return {"ok": False, "reason": "empty task"}
    if ensure_hook:
        try:
            ensure_governance_hook(project_dir, ceiling=ceiling)
        except Exception as e:
            return {"ok": False, "reason": f"could not wire governance hook: {type(e).__name__}"}
    runner = run or (lambda cb, tk, pd, to: _default_run(cb, tk, pd, to, name=name, ceiling=ceiling))
    result = runner(claude_bin, task, project_dir, timeout)
    result.setdefault("governed", True)
    result.setdefault("ceiling", ceiling)
    result.setdefault("approval_mode", approval_mode())
    return result
