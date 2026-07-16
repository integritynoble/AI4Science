"""Find running Claude Code sessions on this machine (read-only).

Lets the machine agent "manage the claude code process": discover live `claude`
processes, their working directory, and whether each is under governance (a
PreToolUse hook wired to the session driver). Finding is read-only; the two
consequential actions — `stop_session` (terminate a runaway) and
`govern_session` (wire the governance hook into a session's project dir) — are
owner-gated at the call site (harness permission gate / owner approval).
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


# --- session introductions (help a human recognize which session is which) ---

def _git_context(cwd: str):
    """Walk up from cwd to find a repo; return (repo_name, branch) or (None, None)."""
    d = cwd
    for _ in range(8):
        g = os.path.join(d, ".git")
        if os.path.isdir(g):
            branch = None
            try:
                head = open(os.path.join(g, "HEAD")).read().strip()
                branch = head.split("/")[-1] if head.startswith("ref:") else head[:7]
            except Exception:
                pass
            return (os.path.basename(d.rstrip("/")) or d, branch)
        if os.path.isfile(g):                          # worktree / submodule pointer
            return (os.path.basename(d.rstrip("/")) or d, None)
        parent = os.path.dirname(d.rstrip("/"))
        if not parent or parent == d:
            break
        d = parent
    return (None, None)


def _proc_start_ago(pid) -> Optional[float]:
    """Seconds since the process started (from /proc/<pid>/stat), or None."""
    try:
        import time
        with open(f"/proc/{int(pid)}/stat") as f:
            after_comm = f.read().rsplit(")", 1)[1].split()
        starttime_ticks = int(after_comm[19])          # field 22 overall, index 19 post-comm
        hz = os.sysconf("SC_CLK_TCK")
        with open("/proc/uptime") as f:
            uptime = float(f.read().split()[0])
        boot = time.time() - uptime
        return max(0.0, time.time() - (boot + starttime_ticks / hz))
    except Exception:
        return None


def _ago(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    s = int(seconds)
    if s < 90:
        return f"{s}s"
    if s < 5400:
        return f"{s // 60}m"
    if s < 172800:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _transcript_path(cwd: str) -> Optional[str]:
    """The newest Claude Code transcript for this project dir, or None. Claude
    stores them at ~/.claude/projects/<cwd-with-slashes-as-dashes>/<id>.jsonl."""
    try:
        import glob
        enc = str(cwd).replace("/", "-")
        base = os.path.expanduser(os.path.join("~", ".claude", "projects", enc))
        files = glob.glob(os.path.join(base, "*.jsonl"))
        return max(files, key=os.path.getmtime) if files else None
    except Exception:
        return None


def _text_of(content) -> Optional[str]:
    if isinstance(content, str):
        return content.strip().replace("\n", " ")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                return part.strip().replace("\n", " ")
            if isinstance(part, dict) and part.get("type") == "text":
                return (part.get("text") or "").strip().replace("\n", " ")
    return None


def _transcript_messages(cwd: str, *, limit: int = 12, tail_bytes: int = 131072):
    """Recent (role, text) pairs from the session's transcript tail — user and
    assistant text turns only (tool results / system-injected turns skipped).
    Own-user only, fail-safe."""
    path = _transcript_path(cwd)
    if not path:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - tail_bytes))
            lines = f.read().decode(errors="replace").splitlines()
    except Exception:
        return []
    out = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        role = obj.get("type")
        if role not in ("user", "assistant"):
            continue
        text = _text_of((obj.get("message") or {}).get("content"))
        if text and not text.startswith("<"):            # skip tool-result / system turns
            out.append((role, text))
    return out[-limit:]


def _session_activity(cwd: str) -> Optional[str]:
    """What the session is currently working on — its most recent user request."""
    for role, text in reversed(_transcript_messages(cwd, limit=20)):
        if role == "user":
            return text[:60]
    return None


def _session_state(cwd: str, *, idle_after: float = 45.0):
    """('working'|'idle', seconds_quiet) from how recently the transcript was
    written. Claude appends to the transcript as it generates and runs tools, so a
    recently-touched transcript means an active task; a quiet one means the session
    is idle, waiting for the next request. None if the transcript is unreadable."""
    path = _transcript_path(cwd)
    if not path:
        return None
    try:
        import time
        quiet = max(0.0, time.time() - os.path.getmtime(path))
    except Exception:
        return None
    return ("working" if quiet < idle_after else "idle", quiet)


def continuation_task(cwd: str) -> Optional[str]:
    """Build a task that resumes a session's work, seeded from its transcript —
    its recent user requests plus where the assistant left off. None if there's
    no readable transcript."""
    msgs = _transcript_messages(cwd, limit=12)
    users = [t for r, t in msgs if r == "user"][-3:]
    if not users:
        return None
    last_assistant = next((t for r, t in reversed(msgs) if r == "assistant"), None)
    parts = ["You are resuming an earlier Claude Code session in THIS directory to finish "
             "its work. Continue autonomously and complete the task.",
             "Recent requests from that session:"]
    parts += [f"  - {u[:220]}" for u in users]
    if last_assistant:
        parts.append(f"Where it left off (last assistant message): {last_assistant[:320]}")
    parts.append("Resume from there and finish the work.")
    return "\n".join(parts)


def describe_session(cwd: Optional[str], args: Optional[List[str]], pid=None) -> str:
    """A short human introduction to a session — project/repo + branch, whether
    it's interactive (and what it's currently working on) or running a headless
    task, and how long it's been running — so a user can tell sessions apart and
    pick the right one."""
    if not cwd:
        return "owned by another user (details hidden)"
    parts = []
    repo, branch = _git_context(cwd)
    if repo:
        parts.append(f"{repo} repo" + (f" @ {branch}" if branch else ""))
    else:
        parts.append(f"in {os.path.basename(cwd.rstrip('/')) or cwd}")
    args = args or []
    if "-p" in args:
        try:
            parts.append(f'task: "{args[args.index("-p") + 1][:48]}"')
        except Exception:
            parts.append("headless")
    else:
        parts.append("interactive")
        activity = _session_activity(cwd)                # what is it actually working on?
        if activity:
            parts.append(f'doing: "{activity}"')
    state = _session_state(cwd)                          # working (in a task) vs idle
    if state:
        label, quiet = state
        parts.append("⏵ WORKING" if label == "working" else f"⏸ idle {_ago(quiet)}")
    ago = _ago(_proc_start_ago(pid)) if pid is not None else None
    if ago:
        parts.append(f"started {ago} ago")
    return " · ".join(parts)


def find_claude_sessions(*, list_procs: Optional[Callable[[], List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Return the running Claude Code sessions this user can see. Each has pid,
    cwd, governance status, and `mine` (True when the cwd is readable — i.e. the
    process is owned by this user and therefore manageable). Fail-safe."""
    list_procs = list_procs or _default_list_procs
    try:
        from ai4science.harness.agents.machine import supervisor as _sup
    except Exception:                                # supervisor optional; degrade gracefully
        _sup = None
    mine, others = [], []
    for p in list_procs():
        cwd = p.get("cwd")
        gov = _governed(cwd)
        rec = None
        if _sup is not None:
            try:
                rec = _sup.get_by_pid(p["pid"])       # join /proc with the supervisor record
            except Exception:
                rec = None
        entry = {"pid": p["pid"], "cwd": cwd,
                 "cmd": " ".join(p.get("args", []))[:120],
                 "intro": describe_session(cwd, p.get("args"), p.get("pid")),
                 "state": (_session_state(cwd) or (None,))[0] if cwd else None,
                 "name": rec["name"] if rec else None,
                 "supervised": rec is not None,
                 "ceiling": (rec.get("ceiling") if rec else gov.get("ceiling")),
                 "governed": bool(rec) or gov.get("governed", False),
                 "via": gov.get("via"),
                 "tripwire": bool(rec and rec.get("tripwire"))}
        (mine if cwd else others).append(entry)      # readable cwd => same-user => manageable
    return {"count": len(mine) + len(others),
            "manageable": mine,                       # the sessions you can act on
            "manageable_count": len(mine),
            "others_count": len(others),              # owned by other users (cwd hidden)
            "summary": summarize(mine, len(others))}


def _cwd_of(pid) -> Optional[str]:
    try:
        return os.readlink(f"/proc/{int(pid)}/cwd")
    except (OSError, PermissionError, ValueError):
        return None


def stop_session(pid, *, sig: Optional[int] = None, kill: Optional[Callable] = None) -> Dict[str, Any]:
    """Send a stop signal to a running Claude session (SIGTERM = graceful). Only
    processes you own. Fail-safe: reports rather than raises. `kill` injectable."""
    import signal as _signal
    kill = kill or os.kill
    sig = _signal.SIGTERM if sig is None else sig
    try:
        kill(int(pid), sig)
    except ProcessLookupError:
        return {"ok": False, "reason": f"no running process {pid}"}
    except PermissionError:
        return {"ok": False, "reason": f"process {pid} is not owned by you — run as its owner to stop it"}
    except (ValueError, TypeError):
        return {"ok": False, "reason": f"invalid pid {pid!r}"}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}"}
    return {"ok": True, "pid": int(pid), "signal": "SIGTERM", "note": "stop signal sent"}


def govern_session(pid, *, ceiling: str = "A1", name: Optional[str] = None,
                   cwd_of: Optional[Callable] = None, wire: Optional[Callable] = None,
                   adopt: Optional[Callable] = None) -> Dict[str, Any]:
    """Adopt a running session: create a durable supervisor record (name, ceiling)
    and wire the governance hook into its project dir. A Claude already running
    there must RESTART to pick it up (hooks load at start); new/restarted sessions
    in that dir are governed. `cwd_of`/`wire`/`adopt` injectable."""
    cwd_of = cwd_of or _cwd_of
    cwd = cwd_of(pid)
    if not cwd:
        return {"ok": False, "reason": f"can't read the project dir of process {pid} "
                                       f"(not owned by you, or it exited)"}
    if wire is None:
        from ai4science.harness.agents.machine.claude_driver import ensure_governance_hook
        wire = ensure_governance_hook
    try:
        path = wire(cwd, ceiling=ceiling)
    except Exception as e:
        return {"ok": False, "reason": f"could not wire hook: {type(e).__name__}"}
    if adopt is None:
        from ai4science.harness.agents.machine import supervisor as _sup
        adopt = _sup.create
    rec = None
    try:                                             # record is best-effort; hook is the gate
        rec = adopt(pid=int(pid), cwd=cwd, name=name, ceiling=ceiling)
    except Exception:
        rec = None
    return {"ok": True, "pid": int(pid), "project_dir": cwd, "settings": str(path),
            "ceiling": ceiling, "name": (rec or {}).get("name"),
            "note": "supervisor attached; governance hook wired in the session's project "
                    "dir. The session already running there must be RESTARTED to pick it "
                    "up; new Claude sessions in this directory are governed."}


def _proc_ancestors(pid) -> set:
    """The pids from `pid` up to init — the process's ancestry."""
    out = set()
    try:
        p = int(pid)
        for _ in range(24):
            out.add(p)
            with open(f"/proc/{p}/stat") as f:
                s = f.read()
            ppid = int(s[s.rfind(")") + 1:].split()[1])
            if ppid <= 1 or ppid == p:
                break
            p = ppid
    except Exception:
        pass
    return out


def tmux_target_for_pid(pid, *, run: Optional[Callable] = None) -> Optional[str]:
    """If `pid` runs inside a tmux pane, return its tmux target (session:win.pane),
    else None. `run(args) -> (stdout, rc)` injectable for tests."""
    run = run or _tmux_list_panes
    try:
        stdout, rc = run(["tmux", "list-panes", "-a", "-F",
                          "#{pane_pid} #{session_name}:#{window_index}.#{pane_index}"])
        if rc != 0:
            return None
        anc = _proc_ancestors(pid)
        for line in stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) in anc:
                return parts[1]
    except Exception:
        return None
    return None


def _tmux_list_panes(args):
    import subprocess
    p = subprocess.run(args, capture_output=True, text=True, timeout=5)
    return p.stdout, p.returncode


def _tmux_send(args):
    import subprocess
    p = subprocess.run(args, capture_output=True, text=True, timeout=5)
    return p.returncode, (p.stderr or "")


def send_to_session(name_or_pid, text: Optional[str] = None, *, enter: bool = True,
                    key: Optional[str] = None, target: Optional[str] = None,
                    resolve: Optional[Callable] = None, run: Optional[Callable] = None) -> Dict[str, Any]:
    """Send keystrokes into a RUNNING tmux-hosted Claude session — answer a native
    prompt or type a task. Resolves name-or-pid to its tmux pane, then runs
    `tmux send-keys`. tmux-only (a bare terminal can't be typed into). Fail-safe.
    `resolve`/`run`/`target` injectable for tests."""
    if resolve is None:
        from ai4science.harness.agents.machine.supervisor import resolve_pid
        resolve = resolve_pid
    pid = resolve(name_or_pid)
    if pid is None:
        s = str(name_or_pid)
        if not s.isdigit():
            return {"ok": False, "reason": f"no session '{name_or_pid}'"}
        pid = int(s)
    if target is None:
        target = tmux_target_for_pid(pid)
    if not target:
        return {"ok": False, "reason": f"session (pid {pid}) is not in tmux — start it with "
                                       f"`tmux new -s <name> claude` to make it drivable"}
    run = run or _tmux_send
    calls = []
    if text:
        calls.append(["tmux", "send-keys", "-t", target, "-l", "--", text])   # literal string
    if key:
        calls.append(["tmux", "send-keys", "-t", target, key])
    if enter:
        calls.append(["tmux", "send-keys", "-t", target, "Enter"])
    if not calls:
        return {"ok": False, "reason": "nothing to send (give text, --key, or Enter)"}
    for a in calls:
        try:
            rc, err = run(a)
        except Exception as e:
            return {"ok": False, "reason": f"{type(e).__name__}"}
        if rc != 0:
            return {"ok": False, "reason": f"tmux send-keys failed: {err[:120]}"}
    sent = (text or "") + (f" {key}" if key else "") + (" ⏎" if enter else "")
    return {"ok": True, "target": target, "pid": pid, "sent": sent.strip()}


def summarize(mine: List[Dict[str, Any]], others_count: int) -> str:
    if not mine and not others_count:
        return "No running Claude Code sessions found."
    lines = []
    if mine:
        lines.append(f"{len(mine)} session(s) (yours):")
        for s in mine:
            name = s.get("name") or "-"
            ceil = s.get("ceiling") or "--"
            state = "TRIPPED" if s.get("tripwire") else ("governed" if s.get("governed") else "NOT governed")
            lines.append(f"  {name:<12} pid {s['pid']}  {s['cwd']}  {ceil}  [{state}]")
            if s.get("intro"):
                lines.append(f"               ↳ {s['intro']}")
    else:
        lines.append("No Claude sessions owned by you (nothing to manage here).")
    if others_count:
        lines.append(f"({others_count} more claude process(es) owned by other users — "
                     f"run as that user or with privileges to inspect them.)")
    return "\n".join(lines)
