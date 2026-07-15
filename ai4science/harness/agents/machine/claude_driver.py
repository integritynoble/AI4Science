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


def _hook_pythonpath() -> Optional[str]:
    """Where the hook (a bare `python -m` subprocess spawned by Claude Code) must
    look to import ai4science — so governance works even when the platform is run
    from source rather than pip-installed. Prepends the ai4science package root to
    any inherited PYTHONPATH."""
    try:
        import ai4science
        root = os.path.dirname(os.path.dirname(os.path.abspath(ai4science.__file__)))
    except Exception:
        return None
    existing = os.environ.get("PYTHONPATH") or ""
    parts = [p for p in existing.split(":") if p]
    if root not in parts:
        parts.insert(0, root)
    return ":".join(parts)


def ensure_governance_hook(project_dir, *, ceiling: str = "A1") -> Path:
    """Write a project .claude/settings.json wiring the PreToolUse governance hook.
    Uses THIS interpreter and embeds PYTHONPATH so the hook resolves ai4science even
    when Claude Code spawns it from an environment without the platform installed."""
    d = Path(project_dir) / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    prefix = f"PWM_CEILING={ceiling}"
    pp = _hook_pythonpath()
    if pp:
        prefix += f" PYTHONPATH={pp}"
    cmd = f"{prefix} {sys.executable} -m ai4science.harness.agents.machine.hook"
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


# --- goal-driven guidance ----------------------------------------------------

def _goal_met(output: str) -> bool:
    """True if the LAST goal signal in the output is GOAL_MET (not GOAL_NOT_MET).
    'GOAL_MET' is not a substring of 'GOAL_NOT_MET', so the two never collide."""
    return output.rfind("GOAL_MET") > output.rfind("GOAL_NOT_MET")


def _guide_prompt(goal: str, *, context: Optional[str] = None, previous: Optional[str] = None) -> str:
    parts = [
        f"GOAL: {goal}",
        "You are working in this directory to achieve the GOAL above. Take whatever "
        "steps are needed — read, edit, run, test, verify — and do NOT stop until the "
        "goal is genuinely met or you are truly blocked.",
        "End your reply with exactly one of these lines:",
        "  GOAL_MET",
        "  GOAL_NOT_MET: <what still remains>",
    ]
    if context:
        parts.append("Context carried over from the session so far:\n" + context)
    if previous:
        parts.append("Your previous round ended with:\n" + previous[-1200:] +
                     "\nContinue from exactly there — do not repeat work already done.")
    return "\n\n".join(parts)


def guide_session(*, project_dir, goal: Optional[str], ceiling: str = "A1",
                  max_rounds: int = 3, timeout: float = 300.0,
                  seed_from_transcript: bool = True,
                  drive: Optional[Callable] = None) -> Dict[str, Any]:
    """Guide a Claude session toward `goal`, round by round, re-driving it (even
    when it has gone idle) until it reports the goal met (GOAL_MET) or `max_rounds`
    is reached. One goal for one session at a time.

    If `goal` is empty, returns {needs_goal: True, question: ...} so the caller can
    ask the user to clarify before guiding. The user is the final judge — the loop
    stops at GOAL_MET and hands the result back for acceptance."""
    if not goal or not str(goal).strip():
        return {"ok": False, "needs_goal": True,
                "question": ("What outcome would satisfy you for this session? Describe the "
                             "goal / done-criteria and I'll guide Claude Code there.")}
    goal = str(goal).strip()
    drive = drive or drive_claude
    log, last = [], ""
    for rnd in range(1, int(max_rounds) + 1):
        ctx = None
        if rnd == 1 and seed_from_transcript:
            try:
                from ai4science.harness.agents.machine.sessions import continuation_task
                ctx = continuation_task(project_dir)
            except Exception:
                ctx = None
        task = _guide_prompt(goal, context=ctx, previous=(last if rnd > 1 else None))
        out = drive(task, project_dir=project_dir, ceiling=ceiling, timeout=timeout)
        last = out.get("output", "") or ""
        met = bool(out.get("ok")) and _goal_met(last)
        log.append({"round": rnd, "ok": bool(out.get("ok")), "met": met, "reason": out.get("reason")})
        if not out.get("ok"):
            return {"ok": False, "met": False, "goal": goal, "rounds": rnd,
                    "reason": out.get("reason"), "output": last, "log": log}
        if met:
            return {"ok": True, "met": True, "goal": goal, "rounds": rnd, "output": last, "log": log}
    return {"ok": True, "met": False, "goal": goal, "rounds": int(max_rounds), "output": last,
            "log": log, "note": "goal not confirmed within the round limit — review and re-run to continue"}
