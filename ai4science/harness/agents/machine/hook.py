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
import tempfile
from typing import Any, Dict, Optional
import sys

from ai4science.harness.agents.machine.session import decide_tool_call


def _tripwire_path(session_id: Optional[str]) -> pathlib.Path:
    """Per-session flag file. A stateless hook runs once per tool call, so the
    'halt the whole session after a forbidden call' behavior is carried across
    invocations by this file (keyed on Claude Code's session_id)."""
    base = os.environ.get("PWM_CP_STATE_DIR") or tempfile.gettempdir()
    return pathlib.Path(base) / "pwm-cc-tripwires" / (session_id or "no-session")


def _is_tripped(session_id: Optional[str]) -> bool:
    try:
        return _tripwire_path(session_id).exists()
    except Exception:
        return False


def _set_tripped(session_id: Optional[str], reason: str) -> None:
    try:
        p = _tripwire_path(session_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(reason or "tripped")
    except Exception:
        pass


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
    call = {"tool_name": data.get("tool_name"), "tool_input": data.get("tool_input", {})}
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd")
    # the supervisor record owns this session's ceiling (resolved by project dir);
    # fall back to the env ceiling when no record is attached.
    ceiling = os.environ.get("PWM_CEILING", "A1")
    rec = None
    try:
        from ai4science.harness.agents.machine import supervisor as _sup
        rec = _sup.get_by_cwd(project_dir) if project_dir else None
        if rec and rec.get("ceiling"):
            ceiling = rec["ceiling"]
    except Exception:
        _sup = None
    # A3 is honored only when earned + unlocked; otherwise capped to A2.
    try:
        from ai4science.harness.agents.machine import trust as _trust
        ceiling = _trust.effective_ceiling(ceiling)
    except Exception:
        _trust = None
    verdict = decide_tool_call(call, ceiling=ceiling, project_dir=project_dir)
    # remote approval channel: escalate an 'ask' to the owner's Telegram if configured
    if verdict.get("decision") == "ask":
        verdict = _maybe_telegram(verdict, data)
    if verdict.get("tripwire"):
        _set_tripped(session_id, verdict.get("reason", ""))
        if _trust is not None:
            try:
                _trust.record("forbidden")           # a catastrophe attempt voids A3 eligibility
            except Exception:
                pass
        if _sup is not None and rec is not None:     # reflect into the record so `session ls` shows TRIPPED
            try:
                _sup.update(rec["name"], tripwire=True, tripwire_reason=verdict.get("reason", ""))
            except Exception:
                pass
    print(json.dumps(verdict_to_hook_output(verdict)))
    return 0


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
