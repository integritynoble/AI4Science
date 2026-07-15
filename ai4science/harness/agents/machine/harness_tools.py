"""Machine-agent operations exposed as harness tools, so the interactive
`machine` agent (in the REPL) calls the REAL governed operations — e.g. finds the
running Claude Code PROCESS — instead of improvising a file search.
"""
from __future__ import annotations

import json

from ai4science.harness.tools.base import Tool


def _find_claude_sessions(workspace) -> str:
    from ai4science.harness.agents.machine.sessions import find_claude_sessions
    return find_claude_sessions()["summary"]


def _detect_machine(workspace) -> str:
    from ai4science.harness.agents.machine.capabilities import detect_machine
    return json.dumps(detect_machine(), indent=2)


def _claude_permissions(workspace) -> str:
    from ai4science.harness.agents.machine.operations import CLAUDE_PERMISSIONS
    return "Claude Code needs these specific permissions: " + ", ".join(CLAUDE_PERMISSIONS)


def _stop_claude_session(workspace, pid) -> str:
    from ai4science.harness.agents.machine.sessions import stop_session
    r = stop_session(pid)
    if r["ok"]:
        return f"Sent SIGTERM to Claude session pid {r['pid']} — {r['note']}."
    return f"Could not stop pid {pid}: {r['reason']}."


def _govern_claude_session(workspace, pid, ceiling="A1") -> str:
    from ai4science.harness.agents.machine.sessions import govern_session
    r = govern_session(pid, ceiling=ceiling)
    if r["ok"]:
        return (f"Wired governance @ {r['ceiling']} into {r['project_dir']} "
                f"({r['settings']}). {r['note']}")
    return f"Could not govern pid {pid}: {r['reason']}."


def machine_tools(ctx) -> list:
    """Machine operations as tools. Read-only discovery (find_claude_sessions /
    detect_machine) plus two owner-gated actions on a running session —
    govern_claude_session and stop_claude_session (mutating=True → the REPL asks
    the owner before they run). Install / permission / login stay behind the
    governed `singularity machine "..."` command; the agent points the user there."""
    return [
        Tool(
            name="find_claude_sessions",
            description=("Find RUNNING Claude Code sessions on this machine (pid, cwd, and "
                         "whether each is governed). Use THIS to detect or manage the Claude "
                         "Code PROCESS — do NOT search for session files."),
            parameters={"type": "object", "properties": {}, "required": []},
            func=_find_claude_sessions, mutating=False,
        ),
        Tool(
            name="detect_machine",
            description=("Detect this machine: OS, arch, and which tools (claude, node, podman, "
                         "git) are installed."),
            parameters={"type": "object", "properties": {}, "required": []},
            func=_detect_machine, mutating=False,
        ),
        Tool(
            name="claude_required_permissions",
            description="List the specific permissions Claude Code needs (least privilege).",
            parameters={"type": "object", "properties": {}, "required": []},
            func=_claude_permissions, mutating=False,
        ),
        Tool(
            name="govern_claude_session",
            description=("Wire the governance hook into a RUNNING Claude session's project dir "
                         "(given its pid, from find_claude_sessions). Takes effect on the next / "
                         "restarted session there — a session already running must be restarted "
                         "to pick it up. Owner-approved."),
            parameters={"type": "object", "properties": {
                "pid": {"type": "integer", "description": "pid of the Claude session to govern"},
                "ceiling": {"type": "string", "enum": ["A0", "A1", "A2"],
                            "description": "capability ceiling to enforce (default A1)"},
            }, "required": ["pid"]},
            func=_govern_claude_session, mutating=True,
        ),
        Tool(
            name="stop_claude_session",
            description=("Stop (terminate, SIGTERM) a RUNNING Claude session by pid — for a "
                         "runaway. Only sessions you own. Consequential and owner-approved: use "
                         "only when asked to stop/kill a session."),
            parameters={"type": "object", "properties": {
                "pid": {"type": "integer", "description": "pid of the Claude session to stop"},
            }, "required": ["pid"]},
            func=_stop_claude_session, mutating=True,
        ),
    ]


MACHINE_SYSTEM_PROMPT = (
    "You are the Machine Agent — you manage this machine and, above all, the Claude "
    "Code process, safely.\n"
    "- To find RUNNING Claude Code sessions, call the `find_claude_sessions` tool "
    "(never search for *session* files — that finds config, not the live process).\n"
    "- To act on a running session, first `find_claude_sessions` to get its pid, then:\n"
    "  • `govern_claude_session(pid)` to wire governance into its project dir — this takes "
    "effect on the next/restarted session there; tell the user the running one must be "
    "restarted to be governed.\n"
    "  • `stop_claude_session(pid)` to terminate a runaway (only sessions the user owns). Use "
    "stop only when the user asks to stop/kill a session — both are owner-approved before they run.\n"
    "- To inspect the machine, call `detect_machine`.\n"
    "- Consequential operations (install Claude Code, grant permissions, log in) are "
    "governed and owner-approved: tell the user to run `singularity machine \"install "
    "claude code\"` (or the relevant intent), or `singularity claude \"<task>\"` to drive "
    "a governed Claude session. Do not try to install or run arbitrary commands yourself."
)
