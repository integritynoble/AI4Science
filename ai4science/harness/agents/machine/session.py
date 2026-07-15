"""Live Claude Code session driver — a governed adjudicator for tool calls.

Interposes on every Claude Code tool call (via the PreToolUse hook): allow safe /
read-only, ASK the owner for consequential, DENY + tripwire the forbidden, audit
all. Fail-safe: anything not positively recognized as read-only defaults to ASK.

This is the runtime "safer than OpenClaw" mechanism — Claude Code never
auto-approves its own consequential actions; the governed policy does.
"""
from __future__ import annotations

import re
import shlex
from typing import Any, Callable, Dict, List, Optional

_CEILING_ORDER = {"A0": 0, "A1": 1, "A2": 2, "A3": 3}

READ_ONLY_TOOLS = {"Read", "Grep", "Glob", "LS", "NotebookRead"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
NETWORK_TOOLS = {"WebFetch", "WebSearch"}

# --- bash command classification --------------------------------------------

_FORBIDDEN = [
    r":\(\)\s*\{.*:\|:.*&.*\}",              # fork bomb
    r"\brm\s+-[a-z]*r[a-z]*f?\s+/(\s|$|\*)",  # rm -rf /
    r"\bmkfs\b", r"\bdd\b[^|]*of=/dev/",
    r">\s*/dev/sd", r"\bchmod\s+-R?\s*777\s+/",
    r"/etc/shadow", r"\b(shutdown|reboot|halt|poweroff)\b",
]
_CONSEQUENTIAL = [
    r"\bsudo\b", r"\brm\s+-[a-z]*r", r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh)\b",
    r"\bgit\s+push\b", r"\b(npm|pnpm|yarn|pip|pip3)\s+(install|publish|add)\b",
    r"\bapt(-get)?\s+(install|remove|purge)\b", r"\b(brew|dnf|yum|pacman)\s+install\b",
    r"\b(docker|podman)\s+(run|build|push|rm)\b", r"\bssh\b", r"\bscp\b", r"\brsync\b",
    r"\bkill(all)?\b", r"\bchmod\b", r"\bchown\b", r">\s*/etc\b", r"\bcrontab\b",
    r"\bexport\b[^=]*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", r"\bdeploy\b",
    r"\bcat\b[^|;&]*(\.env\b|id_rsa|id_ed25519|\.aws/credentials|/etc/passwd)",
]
_SAFE_HEADS = {
    "ls", "cat", "head", "tail", "grep", "rg", "egrep", "fgrep", "find", "pwd",
    "echo", "printf", "wc", "which", "type", "date", "whoami", "id", "uname",
    "hostname", "file", "stat", "du", "df", "tree", "basename", "dirname",
    "true", "false", "test", "sort", "uniq", "cut", "sed", "awk", "diff",
    "cd", "sleep", "seq", "cmp", "realpath", "readlink", "git",
}
_SAFE_GIT = {"status", "log", "diff", "show", "branch", "remote", "config",
             "rev-parse", "ls-files", "describe", "blame", "tag", "stash"}


def classify_command(cmd: str) -> Dict[str, Any]:
    low = (cmd or "").lower()
    for pat in _FORBIDDEN:
        if re.search(pat, low):
            return {"kind": "forbidden", "consequential": True, "reason": "matched a forbidden pattern"}
    for pat in _CONSEQUENTIAL:
        if re.search(pat, low):
            return {"kind": "consequential", "consequential": True, "reason": "matched a consequential pattern"}
    # allowlist: every pipeline/sequence segment must head a read-only command
    segments = re.split(r"[;|]|&&|\|\|", cmd or "")
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        try:
            toks = shlex.split(seg)
        except ValueError:
            return {"kind": "unknown", "consequential": False, "reason": "unparseable command"}
        if not toks:
            continue
        head = toks[0]
        if head not in _SAFE_HEADS:
            return {"kind": "unknown", "consequential": False, "reason": f"unrecognized command {head!r}"}
        if head == "git" and len(toks) > 1 and toks[1] not in _SAFE_GIT:
            return {"kind": "unknown", "consequential": False, "reason": f"non-read-only git: {toks[1]!r}"}
    return {"kind": "read", "consequential": False, "reason": "read-only allowlisted command"}


# --- sensitive path check for writes ----------------------------------------

_SENSITIVE_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/lib", "/var")
_SENSITIVE_SUBSTR = (".ssh/", ".aws/", ".config/gcloud", "credential", "authorized_keys", "/etc/")


def _write_is_sensitive(path: str, project_dir: Optional[str]) -> bool:
    p = (path or "")
    if any(s in p for s in _SENSITIVE_SUBSTR):
        return True
    if p.startswith("/") and any(p.startswith(pre) for pre in _SENSITIVE_PREFIXES):
        return True
    if project_dir and p.startswith("/"):
        import os
        try:
            return os.path.commonpath([os.path.realpath(p), os.path.realpath(project_dir)]) != os.path.realpath(project_dir)
        except Exception:
            return True   # fail-safe
    return False


def _allow(reason): return {"decision": "allow", "reason": reason, "tripwire": False}
def _ask(reason): return {"decision": "ask", "reason": reason, "tripwire": False}
def _deny(reason, tripwire=False): return {"decision": "deny", "reason": reason, "tripwire": tripwire}


def decide_tool_call(call: Dict[str, Any], *, ceiling: str = "A1",
                     project_dir: Optional[str] = None) -> Dict[str, Any]:
    tool = call.get("tool_name") or call.get("tool") or ""
    inp = call.get("tool_input") or call.get("input") or {}
    lvl = _CEILING_ORDER.get(ceiling, 1)

    if tool in READ_ONLY_TOOLS:
        return _allow("read-only tool")

    if tool in NETWORK_TOOLS:                                    # network: >= A1
        return _allow("network (A1+)") if lvl >= 1 else _ask("A0 is advisory; network requires approval")

    if tool in WRITE_TOOLS:
        path = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
        if _write_is_sensitive(path, project_dir):              # sensitive/out-of-project write: >= A2
            return (_allow("sensitive/out-of-project write (A2+)") if lvl >= 2
                    else _ask(f"write to a sensitive/out-of-project path: {path!r}"))
        return _allow("in-project write") if lvl >= 1 else _ask("A0 is advisory; writes require approval")

    if tool == "Bash":
        c = classify_command(inp.get("command", ""))
        if c["kind"] == "forbidden":                            # catastrophe backstop: every tier
            return _deny("forbidden command", tripwire=True)
        if c["kind"] == "consequential":                       # push/install/sudo/…: >= A2
            return _allow("consequential command (A2+)") if lvl >= 2 else _ask(c["reason"])
        if c["kind"] == "unknown":                             # unclassifiable: >= A3
            return _allow("unclassified command (A3)") if lvl >= 3 else _ask(c["reason"])
        return _allow("read-only command") if lvl >= 1 else _ask("A0 is advisory; commands require approval")

    # unmapped tool: >= A3, else fail-safe ask
    return (_allow(f"unmapped tool (A3): {tool!r}") if lvl >= 3
            else _ask(f"unrecognized tool {tool!r}; defaulting to owner approval"))


class SessionDriver:
    """Adjudicates a live Claude Code session's tool calls, halting on a tripwire."""

    def __init__(self, *, ceiling: str = "A1", project_dir: Optional[str] = None,
                 audit: Optional[Callable[[Dict], None]] = None):
        self.ceiling = ceiling
        self.project_dir = project_dir
        self.audit = audit
        self.tripped = False
        self.log: List[Dict] = []

    def drive(self, call: Dict[str, Any]) -> Dict[str, Any]:
        if self.tripped:
            verdict = _deny("session halted by an earlier tripwire", tripwire=True)
        else:
            verdict = decide_tool_call(call, ceiling=self.ceiling, project_dir=self.project_dir)
            if verdict.get("tripwire"):
                self.tripped = True
        entry = {"tool": call.get("tool_name") or call.get("tool"), "verdict": verdict}
        self.log.append(entry)
        if self.audit is not None:
            try:
                self.audit(entry)
            except Exception:
                pass
        return verdict
