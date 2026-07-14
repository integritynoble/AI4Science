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
    verdict = decide_tool_call(
        call,
        ceiling=os.environ.get("PWM_CEILING", "A1"),
        project_dir=os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd"),
    )
    if verdict.get("tripwire"):
        _set_tripped(session_id, verdict.get("reason", ""))
    print(json.dumps(verdict_to_hook_output(verdict)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
