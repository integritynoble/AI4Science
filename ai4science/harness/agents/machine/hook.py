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
import sys
from typing import Any, Dict

from ai4science.harness.agents.machine.session import decide_tool_call


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
    call = {"tool_name": data.get("tool_name"), "tool_input": data.get("tool_input", {})}
    verdict = decide_tool_call(
        call,
        ceiling=os.environ.get("PWM_CEILING", "A1"),
        project_dir=os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd"),
    )
    print(json.dumps(verdict_to_hook_output(verdict)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
