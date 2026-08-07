"""Claude Code `PreToolUse` hook adapter for the governed session driver.

Drop-in wiring: point a `.claude/settings.json` PreToolUse hook at
`python3 -m ai4science.harness.agents.machine.hook`. Claude Code passes the tool
call as JSON on stdin; this emits an allow/ask/deny decision from the governed
policy. The decision engine (`session.decide_tool_call`) is schema-independent —
only this adapter tracks Claude Code's hook format.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Dict, Optional
import sys

from ai4science.harness.agents.machine.session import decide_tool_call


def _tripwire_path(session_id: str) -> pathlib.Path:
    """Per-session flag file. A stateless hook runs once per tool call, so the
    'halt the whole session after a forbidden call' behavior is carried across
    invocations by this file (keyed on Claude Code's session_id)."""
    from ai4science.harness.agents.machine.state import state_dir
    return state_dir() / "pwm-cc-tripwires" / session_id


def _is_tripped(session_id: Optional[str]) -> bool:
    if not session_id:                       # no id → no persistent per-session halt to inherit
        return False
    try:
        return _tripwire_path(session_id).exists()
    except Exception:
        return False


def _set_tripped(session_id: Optional[str], reason: str) -> None:
    if not session_id:                       # don't persist a halt under a shared/absent key
        return
    try:
        p = _tripwire_path(session_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(reason or "tripped")
    except Exception:
        pass


def should_deny(verdict) -> bool:
    """Is this call refused? Unchanged by any scoping below.

    A forbidden command is refused in EVERY session, worker or owner. The
    scoping in this module applies only to the persistent halt.
    """
    return (verdict or {}).get("decision") == "deny"


def should_record_attempt(verdict) -> bool:
    """Should the attempt be written to the trust ledger and the record?

    Always, when a tripwire fired. Scoping the halt must not scope the
    EVIDENCE: a forbidden command was tried, and that it was tried is exactly
    what an owner would never think to check for.
    """
    return bool((verdict or {}).get("tripwire"))


def should_halt_session(verdict, rec) -> bool:
    """Should this session be halted for the rest of its life?

    Only a governed WORKER session, and only on a tripwire.

    `ensure_governance_hook` installs this hook into a project directory, so
    anyone who later runs a coding agent there inherits it -- including the
    owner, at a terminal, working by hand. On 2026-08-07 that happened: a
    `-halt-on-error` FLAG matched the pattern for the `halt` COMMAND and killed
    the owner's session permanently. Every later call, including reading a file,
    returned "session halted by an earlier tripwire".

    The pattern was fixed; the blast radius is the real defect. A false positive
    in a regex should cost ONE DENIED COMMAND, not a working session.

    The discriminator is one this hook already computes. A worker session was
    started on the owner's behalf and has a supervisor record; nobody is
    watching it, so stopping it until the owner looks is right. A session with
    no record was started by a human who is sitting at it: deny the command and
    let them carry on.
    """
    if not (verdict or {}).get("tripwire"):
        return False
    return rec is not None


def _proc_comm_ppid(pid: int):
    with open(f"/proc/{int(pid)}/stat") as f:
        s = f.read()
    comm = s[s.find("(") + 1:s.rfind(")")]
    ppid = int(s[s.rfind(")") + 1:].split()[1])          # field 4 overall (index 1 after comm)
    return comm, ppid


def _ancestor_claude_pid(start=None) -> Optional[int]:
    """Walk up from this hook process to the Claude process that spawned it, so its
    ceiling comes from ITS session's record — not another session sharing the cwd."""
    try:
        pid = int(start) if start is not None else os.getppid()
        for _ in range(16):
            comm, ppid = _proc_comm_ppid(pid)
            if "claude" in comm:
                return pid
            if ppid <= 1 or ppid == pid:
                return None
            pid = ppid
    except Exception:
        return None
    return None


def _session_ceiling(claude_pid, project_dir, env_ceiling, sup):
    """The ceiling for this session: the record for its Claude pid wins, then a
    record for the cwd, then the env ceiling. Returns (ceiling, record)."""
    for rec in (sup.get_by_pid(claude_pid) if claude_pid else None,
                sup.get_by_cwd(project_dir) if project_dir else None):
        if rec and rec.get("ceiling"):
            return rec["ceiling"], rec
    return env_ceiling, None


def verdict_to_hook_output(verdict: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": verdict["decision"],          # allow | ask | deny
            "permissionDecisionReason": verdict.get("reason", ""),
        }
    }


def main(argv=None) -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # fail-safe: on a malformed hook payload, ask the owner rather than allow
        print(json.dumps(verdict_to_hook_output(
            {"decision": "ask", "reason": "unparseable hook payload"})))
        return 0
    session_id = data.get("session_id")
    # if an earlier forbidden call tripped this session, deny everything after it
    if _is_tripped(session_id):
        print(json.dumps(verdict_to_hook_output(
            {"decision": "deny", "reason": "session halted by an earlier tripwire", "tripwire": True})))
        return 0
    # owner pause: hold every action while the machine is paused (not a tripwire — reversible)
    try:
        from ai4science.harness.agents.machine.pause import is_paused
        if is_paused():
            print(json.dumps(verdict_to_hook_output(
                {"decision": "deny", "reason": "paused by owner — resume with `singularity session resume`",
                 "tripwire": False})))
            return 0
    except Exception:
        pass
    call = {"tool_name": data.get("tool_name"), "tool_input": data.get("tool_input", {})}
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd")
    # Resolve THIS session's ceiling from its supervisor record. The hook is a
    # child of the Claude process making the call, so match by that ancestor pid
    # first (precise when several sessions share a cwd), then fall back to cwd,
    # then the env ceiling.
    ceiling = os.environ.get("PWM_CEILING", "A1")
    rec = None
    try:
        from ai4science.harness.agents.machine import supervisor as _sup
        ceiling, rec = _session_ceiling(_ancestor_claude_pid(), project_dir, ceiling, _sup)
    except Exception:
        _sup = None
    # A3 is honored only when earned + unlocked; otherwise capped to A2.
    try:
        from ai4science.harness.agents.machine import trust as _trust
        ceiling = _trust.effective_ceiling(ceiling)
    except Exception:
        _trust = None
    verdict = decide_tool_call(call, ceiling=ceiling, project_dir=project_dir,
                               writable=_declared_writable())
    # remote approval channel: escalate an 'ask' to the owner's Telegram if configured
    if verdict.get("decision") == "ask":
        verdict = _maybe_telegram(verdict, data)
    if should_record_attempt(verdict):
        # The HALT is scoped to worker sessions; the deny and the record are
        # not. See `should_halt_session` for why the owner's own session must
        # survive a false positive.
        if should_halt_session(verdict, rec):
            _set_tripped(session_id, verdict.get("reason", ""))
        # The deny is already decided and is printed either way, so the command
        # is blocked regardless of what follows. What used to vanish silently
        # is the RECORD of the attempt — the trust entry that voids A3
        # eligibility, and the flag that makes a tripped session visible in
        # `session ls`. A forbidden command was tried; the owner's evidence
        # that it was tried is exactly what would be missed and never looked
        # for.
        #
        # Refusing is not available here: this hook is a subprocess Claude Code
        # depends on, and raising would leave it with no verdict at all, which
        # is a worse failure than an unrecorded one. So the gap goes into the
        # REASON, the one channel that always reaches the surface.
        unrecorded = []
        if _trust is not None:
            try:
                _trust.record("forbidden")           # a catastrophe attempt voids A3 eligibility
            except Exception:
                unrecorded.append("the trust ledger (A3 eligibility not voided)")
        if _sup is not None and rec is not None:     # reflect into the record so `session ls` shows TRIPPED
            try:
                _sup.update(rec["name"], tripwire=True, tripwire_reason=verdict.get("reason", ""))
            except Exception:
                unrecorded.append("the session record (`session ls` will not "
                                  "show this session as TRIPPED)")
        verdict = _note_record_failures(verdict, unrecorded)
    print(json.dumps(verdict_to_hook_output(verdict)))
    return 0


def _declared_writable() -> list:
    """The paths this task declared, as the session was launched with them.

    Empty when unset — NOT `[""]`, which would resolve to the process's cwd,
    whatever launched the daemon. "Nothing was declared" and "the current
    directory was declared" are very different permissions.
    """
    import os
    raw = (os.environ.get("PWM_WRITABLE") or "").strip()
    return [p for p in raw.split(os.pathsep) if p.strip()] if raw else []


def _note_record_failures(verdict: Dict[str, Any], unrecorded) -> Dict[str, Any]:
    """Say, in the verdict, which records of this tripwire could not be written.

    The decision is untouched — a block is not traded for a note. This only
    ensures that "it fired and nobody wrote it down" cannot happen quietly.
    """
    if not unrecorded:
        return verdict
    out = dict(verdict)
    out["reason"] = (f"{verdict.get('reason', '')} — WARNING: this attempt "
                     f"could not be recorded in {', '.join(unrecorded)}").strip()
    out["unrecorded"] = list(unrecorded)
    return out


def _maybe_telegram(verdict: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """When Telegram is configured, turn an 'ask' into an owner Approve/Deny tap.
    Any error or timeout fails safe to deny; unconfigured leaves 'ask' as-is."""
    from ai4science.harness.agents.machine.telegram import telegram_config, request_approval
    cfg = telegram_config()
    if not cfg:
        return verdict
    token, chat_id, owner_id = cfg
    tool = data.get("tool_name", "?")
    detail = json.dumps(data.get("tool_input", {}))[:300]
    text = (f"Claude Code wants to run:\n{tool}: {detail}\n"
            f"Reason: {verdict.get('reason', '')}\nApprove?")
    request_id = str(data.get("tool_use_id") or data.get("session_id") or "req")
    try:
        timeout = float(os.environ.get("PWM_TELEGRAM_TIMEOUT", "55"))
        approved = request_approval(text, token=token, chat_id=chat_id, owner_id=owner_id,
                                    request_id=request_id, timeout=timeout)
    except Exception:
        approved = None
    try:                                             # a resolved owner decision feeds the trust ledger
        if approved in (True, False):
            from ai4science.harness.agents.machine import trust as _trust
            _trust.record("approve" if approved is True else "deny")
    except Exception:
        pass
    if approved is True:
        return {"decision": "allow", "reason": "approved by owner via Telegram", "tripwire": False}
    return {"decision": "deny",
            "reason": "denied by owner via Telegram" if approved is False
                      else "no Telegram approval (timeout/error) — fail-safe deny",
            "tripwire": False}


if __name__ == "__main__":
    raise SystemExit(main())
