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

READ_ONLY_TOOLS = {"Read", "Grep", "Glob", "LS", "NotebookRead",
                   # Claude Code's own bookkeeping (its internal todo/task list
                   # + planning) — no side effects outside the session; without
                   # these, plan-mode re-prompts the owner on EVERY step
                   "TodoWrite", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
                   "TaskOutput", "TaskStop", "ToolSearch", "EnterPlanMode",
                   "ExitPlanMode", "AskUserQuestion", "Skill"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
NETWORK_TOOLS = {"WebFetch", "WebSearch"}

# --- bash command classification --------------------------------------------

_FORBIDDEN = [
    r":\(\)\s*\{.*:\|:.*&.*\}",              # fork bomb
    r"\brm\s+-[a-z]*r[a-z]*f?\s+/(\s|$|\*)",  # rm -rf /
    r"\bmkfs\b", r"\bdd\b[^|]*of=/dev/",
    r">\s*/dev/sd", r"\bchmod\s+-R?\s*777\s+/",
    # (?<!-) / (?!-) : a flag like `-halt-on-error` or a path like
    # /var/run/reboot-required is not an invocation of the command.
    r"/etc/shadow", r"(?<!-)\b(shutdown|reboot|halt|poweroff)\b(?!-)",
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
# `sed`/`awk` are NOT here: both can execute arbitrary code (awk system()/getline,
# GNU sed `e`), so they are gated as unknown (A3) rather than treated as read-only.
_SAFE_HEADS = {
    "ls", "cat", "head", "tail", "grep", "rg", "egrep", "fgrep", "find", "pwd",
    "echo", "printf", "wc", "which", "type", "date", "whoami", "id", "uname",
    "hostname", "file", "stat", "du", "df", "tree", "basename", "dirname",
    "true", "false", "test", "sort", "uniq", "cut", "tr", "diff",
    "cd", "sleep", "seq", "cmp", "realpath", "readlink", "git",
}

# in-project WORK commands — running the project (interpreters, tests, builds).
# Same trust tier as the Write tool: A1 = in-project autonomy. Forbidden /
# consequential / protected patterns are checked BEFORE this, so installs,
# sudo, pushes etc. stay gated regardless of the interpreter head.
_WORK_HEADS = {"python", "python3", "pytest", "uv", "node", "npm", "npx", "make"}
_SAFE_GIT = {"status", "log", "diff", "show", "branch", "remote", "config",
             "rev-parse", "ls-files", "describe", "blame", "tag", "stash"}
_FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprintf",
              "-fprint", "-fprint0", "-fls"}

# Governance config + owner state the governed agent must never rewrite — writing
# any of these lets it remove its own hook or lift its own ceiling, so they are
# DENIED at every ceiling (reads are unaffected).
_PROTECTED_WRITE = (".claude/settings.json", ".claude/settings.local.json",
                    "pwm-cc-trust", "pwm-cc-tripwires", "pwm-cc-sessions", "/pwm-cp/")
# `\b` treats '-' as a word boundary, so `\bcp\b` matched the "cp" inside our own
# state dir name (pwm-cp) and any command naming it read as a copy. Require each
# verb to stand alone — not glued to a word char OR a hyphen on either side.
_WRITE_VERB = re.compile(
    r">|(?<![\w-])(?:tee|dd|rm|mv|cp|ln|truncate|chmod|chown)(?![\w-])")
_SEG_SPLIT = re.compile(r"[;|&]+")


def _write_is_protected(path: str) -> bool:
    return any(s in (path or "") for s in _PROTECTED_WRITE)


def _bash_writes_protected(cmd: str) -> bool:
    """A bash command that WRITES (redirect / tee / rm / mv …) to a protected path.
    Reading a protected file (cat/grep) is fine and not flagged.

    A protected-path substring and a write-verb match ANYWHERE in the command
    used to be enough — but `2>/dev/null` on an unrelated read contains a bare
    '>' too, so a plain `cat .../.claude/settings.json 2>/dev/null` was flagged
    as writing to it. Only a write-verb match on the SAME SIDE of (before) a
    protected-path mention counts: a verb that appears after the path can't be
    the thing writing to it.

    Position alone is still too coarse across a compound command: in
    `cat x 2>/dev/null; ls .../pwm-cc-trust` the '>' precedes the path but
    belongs to a DIFFERENT segment, so it cannot be writing it either. Scope the
    verb search to the segment the path appears in — a write and its target
    always share one segment.
    """
    if not any(s in cmd for s in _PROTECTED_WRITE):
        return False
    for seg in _SEG_SPLIT.split(cmd or ""):
        for s in _PROTECTED_WRITE:
            start = 0
            while True:
                idx = seg.find(s, start)
                if idx == -1:
                    break
                if _WRITE_VERB.search(seg[:idx]):
                    return True
                start = idx + 1
    return False


_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def _strip_heredocs(cmd: str) -> str:
    """Remove heredoc BODIES — data being written, not commands to run."""
    out, rest = [], cmd or ""
    while True:
        m = _HEREDOC_RE.search(rest)
        if not m:
            out.append(rest)
            break
        out.append(rest[:m.start()])
        marker, tail = m.group(2), rest[m.end():]
        end = re.search(r"^\s*%s\s*$" % re.escape(marker), tail, re.M)
        rest = tail[end.end():] if end else ""
    return " ".join(out)


def _blank_quoted(text: str) -> str:
    """A quoted string is an operand. `git commit -m "…"` runs git, whatever
    the message says."""
    return _QUOTED_RE.sub("''", text or "")


def classify_command(cmd: str) -> Dict[str, Any]:
    """Classify what would EXECUTE, not the raw text of the command.

    Matching the raw string halts a session for WRITING about a forbidden
    pattern. On 2026-08-03 that happened four times on one host: a session
    documenting this governor, two writing tests for it, and one whose commit
    message contained the word `halt`. None of them ran anything, and each lost
    every tool it had — including Read, so it could not inspect its own work.

    Heredoc bodies and quoted literals are removed before matching. A real
    attempt is unaffected: it is neither quoted nor inside a heredoc.
    """
    low = _blank_quoted(_strip_heredocs(cmd or "")).lower()
    for pat in _FORBIDDEN:
        if re.search(pat, low):
            return {"kind": "forbidden", "consequential": True, "reason": "matched a forbidden pattern"}
    for pat in _CONSEQUENTIAL:
        if re.search(pat, low):
            return {"kind": "consequential", "consequential": True, "reason": "matched a consequential pattern"}
    if _bash_writes_protected(low):
        return {"kind": "protected", "consequential": True,
                "reason": "writes a protected governance/state path"}
    # allowlist: every pipeline/sequence segment must head a read-only or work
    # command. Split QUOTE-AWARE — a | inside quotes (grep "a|b") is data, not a
    # pipe; the old regex split broke quoting and mis-flagged such commands as
    # unparseable.
    work_seen = False
    try:
        lex = shlex.shlex(cmd or "", posix=True, punctuation_chars="|&;<>")
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return {"kind": "unknown", "consequential": False, "reason": "unparseable command"}
    segments: List[List[str]] = [[]]
    for t in tokens:
        if t and all(c in "|&;" for c in t):        # pipe/sequence operator
            segments.append([])
        elif t and all(c in "<>&" for c in t):      # redirection — not a new segment
            continue
        else:
            segments[-1].append(t)
    for toks in segments:
        if not toks:
            continue
        # `VAR=value cmd ...` is a shell prefix, not the command itself — strip
        # leading assignments so e.g. `D=/tmp grep ...` classifies on `grep`,
        # not on the assignment token (which matches no known head).
        i = 0
        while i < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i]):
            i += 1
        toks = toks[i:]
        if not toks:
            continue
        head = toks[0]
        if head not in _SAFE_HEADS and head not in _WORK_HEADS:
            return {"kind": "unknown", "consequential": False, "reason": f"unrecognized command {head!r}"}
        if head in _WORK_HEADS:
            work_seen = True
        if head == "git" and len(toks) > 1 and toks[1] not in _SAFE_GIT:
            return {"kind": "unknown", "consequential": False, "reason": f"non-read-only git: {toks[1]!r}"}
        if head == "find" and any(t in _FIND_EXEC for t in toks[1:]):
            return {"kind": "unknown", "consequential": False, "reason": "find with -exec/-delete"}
    if work_seen:
        return {"kind": "work", "consequential": False, "reason": "in-project work command (run/test/build)"}
    return {"kind": "read", "consequential": False, "reason": "read-only allowlisted command"}


# --- sensitive path check for writes ----------------------------------------

_SENSITIVE_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/lib", "/var")
_SENSITIVE_SUBSTR = (".ssh/", ".aws/", ".config/gcloud", "credential", "authorized_keys", "/etc/")


def _is_sensitive_by_name(path: str) -> bool:
    """Sensitive because of WHAT it is — `/etc`, `.ssh`, a credential — rather
    than because of where the project happens to be. Declaring one of these as
    a working directory does not unlock it."""
    p = (path or "")
    if any(sub in p for sub in _SENSITIVE_SUBSTR):
        return True
    return p.startswith("/") and any(p.startswith(pre)
                                     for pre in _SENSITIVE_PREFIXES)


def _within_declared(path: str, writable) -> bool:
    """Is *path* inside a root the task DECLARED and the owner granted?

    Compared as resolved paths, never as strings: `/x/work-evil` shares six
    characters with `/x/work` and is not inside it.
    """
    import os
    if not writable or not path:
        return False
    try:
        target = os.path.realpath(path)
    except Exception:
        return False
    for root in writable:
        try:
            real = os.path.realpath(str(root))
        except Exception:
            continue
        if target == real:
            continue                      # the directory itself is not a file
        if os.path.commonpath([target, real]) == real:
            return True
    return False


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


def _capped_by_group(ceiling: str, group) -> str:
    """The declared ceiling, capped by the group's — never widened by it.

    A research agent is a group, and "the ceiling belongs to the act, and the act
    with a body sets it": a group holding one embodied member sits at A0 however
    the agent was declared. Until now `Group.capped` was consulted only by the
    two renderers (`commands/research.py`, `sarsi/board.py`), so the rule was
    DESCRIPTIVE — a sentence printed on a board while the grant path went on
    honoring the agent's own letter. A rule only a renderer reads is not a
    ceiling; this is where it stops being descriptive.

    Duck-typed on purpose: anything with `.capped(str) -> str` will do. Nothing
    from `research_agents` may be imported here — `group.py` imports
    `_CEILING_ORDER` FROM this module, so importing back is a cycle.

    A malformed group must never widen authority, so a `.capped()` that raises,
    or that answers with something outside `_CEILING_ORDER`, falls back to the
    DECLARED ceiling rather than to anything higher. Same shape as the
    `_trust.effective_ceiling` cap in `hook.py`, which lowers A3 to A2 when A3 is
    not unlocked: a cap applied to the ceiling before any level is read from it.
    """
    try:
        capped = group.capped(ceiling)
    except Exception:
        return ceiling
    if capped not in _CEILING_ORDER:
        return ceiling
    # belt and braces: take the lower of the two, so a `capped()` that answers
    # upward is ignored rather than obeyed.
    return min((ceiling, capped),
               key=lambda c: _CEILING_ORDER.get(c, 1))


def decide_tool_call(call: Dict[str, Any], *, ceiling: str = "A1",
                     project_dir: Optional[str] = None,
                     writable=None, group=None) -> Dict[str, Any]:
    tool = call.get("tool_name") or call.get("tool") or ""
    inp = call.get("tool_input") or call.get("input") or {}
    # The cap lands BEFORE `lvl` — every branch below reads `lvl`, so a cap
    # applied anywhere later would be a cap on some decisions and not others.
    if group is not None:
        ceiling = _capped_by_group(ceiling, group)
    lvl = _CEILING_ORDER.get(ceiling, 1)

    if tool in READ_ONLY_TOOLS:
        return _allow("read-only tool")

    if tool in NETWORK_TOOLS:                                    # network: >= A1
        return _allow("network (A1+)") if lvl >= 1 else _ask("A0 is advisory; network requires approval")

    if tool in WRITE_TOOLS:
        path = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
        if _write_is_protected(path):                          # governor config / owner state: never
            return _deny("writing a governance/state path (hook config or trust ledger) is not permitted")
        if _write_is_sensitive(path, project_dir):
            # A2 is trusted to WORK, not trusted to write anywhere. It is what
            # `release` gives every task, so it was the standing authority of
            # an ordinary run — and for a claude-code session this hook is the
            # ONLY boundary in force, which made `/etc/passwd` an allow.
            #
            # A path the task DECLARED and the owner granted is in-project by
            # agreement: the session now stands in the working directory, so
            # its own task folder is out of project, and without this every
            # `plan0.md` edit would ask with nothing left to answer it. Two
            # boundaries that disagree are one boundary and one blind spot.
            #
            # Declaring does NOT reach a genuinely sensitive path — `/etc`,
            # `.ssh`, credentials. A path that can authorise itself is the hole
            # the declaration exists to close.
            if (not _is_sensitive_by_name(path)
                    and _within_declared(path, writable)):
                return (_allow("a write inside a declared path (A1+)")
                        if lvl >= 1
                        else _ask("A0 is advisory; writes require approval"))
            return _ask(f"write to a sensitive/out-of-project path: {path!r}")
        return _allow("in-project write") if lvl >= 1 else _ask("A0 is advisory; writes require approval")

    if tool == "Bash":
        c = classify_command(inp.get("command", ""))
        if c["kind"] == "forbidden":                            # catastrophe backstop: every tier
            return _deny("forbidden command", tripwire=True)
        if c["kind"] == "protected":                           # governor config / owner state: never
            return _deny("command writes a governance/state path — not permitted")
        if c["kind"] == "consequential":                       # push/install/sudo/…: >= A2
            return _allow("consequential command (A2+)") if lvl >= 2 else _ask(c["reason"])
        if c["kind"] == "work":                                # run/test/build: >= A1
            return _allow("in-project work command (A1+)") if lvl >= 1 else _ask("A0 is advisory; running the project requires approval")
        if c["kind"] == "unknown":                             # unclassifiable: >= A3
            return _allow("unclassified command (A3)") if lvl >= 3 else _ask(c["reason"])
        return _allow("read-only command") if lvl >= 1 else _ask("A0 is advisory; commands require approval")

    # unmapped tool: >= A3, else fail-safe ask
    return (_allow(f"unmapped tool (A3): {tool!r}") if lvl >= 3
            else _ask(f"unrecognized tool {tool!r}; defaulting to owner approval"))


class SessionDriver:
    """Adjudicates a live Claude Code session's tool calls, halting on a tripwire."""

    def __init__(self, *, ceiling: str = "A1", project_dir: Optional[str] = None,
                 audit: Optional[Callable[[Dict], None]] = None, group=None):
        self.ceiling = ceiling
        self.project_dir = project_dir
        self.audit = audit
        #: Optional group whose ceiling caps this session's — duck-typed,
        #: `.capped(str) -> str`. See `_capped_by_group`.
        self.group = group
        self.tripped = False
        self.log: List[Dict] = []

    def effective_ceiling(self) -> str:
        """What this session actually runs at — the declared ceiling capped by
        the group's, if it has one. Named for `trust.effective_ceiling`, which
        does the same job for the trust ledger: what was asked for is not
        necessarily what is in force, and a caller that wants to SAY the ceiling
        should say this one."""
        if self.group is None:
            return self.ceiling
        return _capped_by_group(self.ceiling, self.group)

    def drive(self, call: Dict[str, Any]) -> Dict[str, Any]:
        if self.tripped:
            verdict = _deny("session halted by an earlier tripwire", tripwire=True)
        else:
            verdict = decide_tool_call(call, ceiling=self.ceiling,
                                       project_dir=self.project_dir,
                                       group=self.group)
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
