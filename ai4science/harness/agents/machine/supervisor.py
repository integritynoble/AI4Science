"""Durable per-session supervisor records — one per Claude Code session.

Each running Claude session owns a durable record (name, pid, cwd, ceiling,
tripwire/trust state). The record is the session's *authority*: it persists as
long as the OS process lives, so a supervisor/watcher process may restart and
re-attach without orphaning the session. The machine agent is the fleet manager
over these records. Everything here is fail-safe — reads never raise.

State lives under `$PWM_CP_STATE_DIR/pwm-cc-sessions/<name>.json` (same state dir
as the hook's tripwire flags).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _sessions_dir() -> Path:
    from ai4science.harness.agents.machine.state import state_dir
    return state_dir() / "pwm-cc-sessions"


def _record_path(name: str) -> Path:
    return _sessions_dir() / f"{name}.json"


def _pid_alive(pid) -> bool:
    """True if the process exists. A PermissionError means it exists but is owned
    by another user — still alive for our purposes."""
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (ValueError, TypeError):
        return False


_NAME_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    s = _NAME_RE.sub("-", (text or "").lower()).strip("-")
    return s or "session"


def default_name(cwd: str) -> str:
    return _slug(os.path.basename(str(cwd).rstrip("/")))


def _iso(t: float) -> str:
    return (datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc)
            .replace(microsecond=0).isoformat())


def _read(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write(rec: Dict[str, Any]) -> None:
    try:
        _sessions_dir().mkdir(parents=True, exist_ok=True)
        _record_path(rec["name"]).write_text(json.dumps(rec, indent=2))
    except Exception:
        pass


# --- queries ----------------------------------------------------------------

def list_all() -> List[Dict[str, Any]]:
    try:
        files = sorted(_sessions_dir().glob("*.json"))
    except Exception:
        return []
    return [r for r in (_read(f) for f in files) if r]


def list_live(*, alive: Callable = _pid_alive) -> List[Dict[str, Any]]:
    reap(alive=alive)
    return [r for r in list_all() if alive(r.get("pid"))]


def get_by_name(name) -> Optional[Dict[str, Any]]:
    return _read(_record_path(_slug(str(name))))


def get_by_pid(pid) -> Optional[Dict[str, Any]]:
    try:
        p = int(pid)
    except (ValueError, TypeError):
        return None
    for r in list_all():
        if r.get("pid") == p:
            return r
    return None


def _records_for_cwd(target: str, alive=None) -> list:
    """Every record whose cwd resolves to `target`."""
    out = []
    for r in list_all():
        try:
            if os.path.realpath(r.get("cwd", "")) == target:
                out.append(r)
        except Exception:
            continue
    return out


def get_by_cwd(cwd, alive=None) -> Optional[Dict[str, Any]]:
    """Resolve a record by project dir — the key the stateless hook uses (it
    knows cwd, not the record name).

    **Refuses to answer when live records for this directory disagree about
    the ceiling.** Two sessions sharing a working directory is legitimate, and
    this is the hook's fallback when its pid walk fails; picking one
    arbitrarily hands a session an authority level nobody set for it, silently
    and in either direction. Observed live: an A1 and an A2 record shared a
    cwd, and this returned the A1 one.

    Returning None is the safer failure. The hook then falls through to its
    declared env ceiling, which is deterministic and inspectable, instead of
    an arbitrary pick that looks authoritative. Only a genuine DISAGREEMENT is
    unanswerable — records that agree still resolve, and dead records never
    make a live one unresolvable.
    """
    try:
        target = os.path.realpath(str(cwd))
    except Exception:
        return None
    is_alive = alive or _pid_alive
    rows = _records_for_cwd(target)
    if not rows:
        return None
    live = [r for r in rows if is_alive(r.get("pid"))]
    pool = live or rows
    ceilings = {r.get("ceiling") for r in pool if r.get("ceiling")}
    if len(ceilings) > 1:
        return None                      # ambiguous — say nothing rather than guess
    return pool[0]


def ceiling_report(alive=None) -> list:
    """What each record's ceiling is RECORDED as, beside what would actually be
    RESOLVED for it — and by which path.

    Nothing surfaced this before, which is how a drift between the two sat
    unnoticed for days and was then misread as harmless. `by` names the rung of
    the hook's own chain that answers: `pid` (exact), `cwd` (the shared-directory
    fallback), or `none` (nothing resolves, so the declared env ceiling applies).

    `cwd_ambiguous` marks a directory more than one live record claims — the
    condition that makes the `cwd` rung unusable, and therefore the thing to fix
    before a pid ever goes stale.
    """
    is_alive = alive or _pid_alive
    rows = []
    for r in list_all():
        pid, cwd = r.get("pid"), r.get("cwd") or ""
        try:
            target = os.path.realpath(cwd)
        except Exception:
            target = cwd
        peers = [p for p in _records_for_cwd(target) if is_alive(p.get("pid"))]
        ambiguous = len({p.get("ceiling") for p in peers if p.get("ceiling")}) > 1
        pid_ok = bool(pid) and is_alive(pid)
        if pid_ok:
            by, resolved = "pid", r.get("ceiling")
        else:
            hit = get_by_cwd(cwd, alive=is_alive)
            by, resolved = ("cwd", hit.get("ceiling")) if hit else ("none", None)
        rows.append({"name": r.get("name"), "cwd": cwd, "pid": pid,
                     "pid_alive": pid_ok, "recorded": r.get("ceiling"),
                     "resolved": resolved, "by": by,
                     "agrees": resolved == r.get("ceiling"),
                     "cwd_ambiguous": ambiguous})
    return rows


def get(name_or_pid) -> Optional[Dict[str, Any]]:
    s = str(name_or_pid).strip()
    return get_by_pid(s) if s.isdigit() else get_by_name(s)


def resolve_pid(name_or_pid) -> Optional[int]:
    """Turn a name-or-pid into a pid (for stop/govern). Returns None if unknown."""
    s = str(name_or_pid).strip()
    if s.isdigit():
        return int(s)
    r = get_by_name(s)
    return int(r["pid"]) if r else None


# --- lifecycle --------------------------------------------------------------

def _unique_name(preferred: str, *, taken: set) -> str:
    if preferred not in taken:
        return preferred
    i = 2
    while f"{preferred}-{i}" in taken:
        i += 1
    return f"{preferred}-{i}"


def create(*, pid, cwd, name: Optional[str] = None, ceiling: str = "A1",
           session_id: Optional[str] = None, now: Callable[[], float] = time.time,
           alive: Callable = _pid_alive) -> Dict[str, Any]:
    """Create (or return the existing) supervisor record for a session. Allocates
    a unique name (default: the cwd basename; collisions get a -N suffix). If a
    record already exists for this pid, it is returned unchanged. Fail-safe."""
    reap(alive=alive)
    existing = get_by_pid(pid)
    if existing:
        return existing
    taken = {r["name"] for r in list_all()}
    base = _slug(name) if name else default_name(cwd)
    rec = {"name": _unique_name(base, taken=taken), "pid": int(pid), "cwd": str(cwd),
           "session_id": session_id, "ceiling": ceiling, "started_at": _iso(now()),
           "status": "live", "goal": None, "tripwire": False, "tripwire_reason": None,
           "approvals": 0, "denials": 0, "forbidden_trips": 0}
    _write(rec)
    return rec


def update(name_or_pid, **fields) -> Optional[Dict[str, Any]]:
    """Patch fields on a record (ceiling, tripwire, trust counters). Fail-safe."""
    r = get(name_or_pid)
    if not r:
        return None
    r.update(fields)
    _write(r)
    return r


def close(name_or_pid) -> bool:
    """Remove a session's record, releasing its name. Fail-safe."""
    r = get(name_or_pid)
    if not r:
        return False
    try:
        _record_path(r["name"]).unlink()
        return True
    except Exception:
        return False


def reap(*, alive: Callable = _pid_alive) -> List[str]:
    """Delete records whose process has exited (a session that died without a
    clean close). Returns the reaped names."""
    reaped: List[str] = []
    for r in list_all():
        if not alive(r.get("pid")):
            try:
                _record_path(r["name"]).unlink()
                reaped.append(r["name"])
            except Exception:
                pass
    return reaped
