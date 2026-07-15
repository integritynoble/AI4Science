"""Find running Claude Code sessions on this machine (read-only).

Lets the machine agent "manage the claude code process": discover live `claude`
processes, their working directory, and whether each is under governance (a
PreToolUse hook wired to the session driver). No mutation.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional


def _proc_args(pid: str) -> Optional[List[str]]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except (OSError, PermissionError):
        return None
    if not raw:
        return None
    return [a for a in raw.decode(errors="replace").split("\x00") if a]


def _looks_like_claude(args: List[str]) -> bool:
    # the claude CLI, launched directly or via node (argv has a path ending /claude)
    for a in args:
        if a.rsplit("/", 1)[-1] == "claude":
            return True
    return False


def _default_list_procs() -> List[Dict[str, Any]]:
    procs: List[Dict[str, Any]] = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return procs
    for pid in pids:
        args = _proc_args(pid)
        if not args or not _looks_like_claude(args):
            continue
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except (OSError, PermissionError):
            cwd = None
        procs.append({"pid": int(pid), "args": args, "cwd": cwd})
    return procs


def _hook_command(settings_path: str) -> Optional[str]:
    try:
        s = json.load(open(settings_path))
    except Exception:
        return None
    for grp in s.get("hooks", {}).get("PreToolUse", []):
        for h in grp.get("hooks", []):
            cmd = h.get("command", "")
            if "machine.hook" in cmd:
                return cmd
    return None


def _governed(cwd: Optional[str]) -> Dict[str, Any]:
    """Governed if the session driver's PreToolUse hook is wired in the project's
    .claude/settings.json or the user's ~/.claude/settings.json."""
    candidates = []
    if cwd:
        candidates.append(os.path.join(cwd, ".claude", "settings.json"))
    candidates.append(os.path.expanduser("~/.claude/settings.json"))
    for path in candidates:
        cmd = _hook_command(path)
        if cmd:
            return {"governed": True, "via": path, "ceiling": _ceiling_of(cmd)}
    return {"governed": False}


def _ceiling_of(cmd: str) -> Optional[str]:
    for tok in cmd.split():
        if tok.startswith("PWM_CEILING="):
            return tok.split("=", 1)[1]
    return None


def find_claude_sessions(*, list_procs: Optional[Callable[[], List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Return the running Claude Code sessions this user can see. Each has pid,
    cwd, governance status, and `mine` (True when the cwd is readable — i.e. the
    process is owned by this user and therefore manageable). Fail-safe."""
    list_procs = list_procs or _default_list_procs
    mine, others = [], []
    for p in list_procs():
        cwd = p.get("cwd")
        entry = {"pid": p["pid"], "cwd": cwd,
                 "cmd": " ".join(p.get("args", []))[:120], **_governed(cwd)}
        (mine if cwd else others).append(entry)      # readable cwd => same-user => manageable
    return {"count": len(mine) + len(others),
            "manageable": mine,                       # the sessions you can act on
            "manageable_count": len(mine),
            "others_count": len(others),              # owned by other users (cwd hidden)
            "summary": summarize(mine, len(others))}


def summarize(mine: List[Dict[str, Any]], others_count: int) -> str:
    if not mine and not others_count:
        return "No running Claude Code sessions found."
    lines = []
    if mine:
        lines.append(f"{len(mine)} manageable Claude session(s) (yours):")
        for s in mine:
            gov = f"governed @ {s.get('ceiling')}" if s.get("governed") else "NOT governed"
            lines.append(f"  • pid {s['pid']}  in {s['cwd']}  [{gov}]")
    else:
        lines.append("No Claude sessions owned by you (nothing to manage here).")
    if others_count:
        lines.append(f"({others_count} more claude process(es) owned by other users — "
                     f"run as that user or with privileges to inspect them.)")
    return "\n".join(lines)
