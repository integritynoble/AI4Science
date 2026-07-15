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


def machine_tools(ctx) -> list:
    """Read-only machine operations as tools. Consequential ops (install /
    permission / login) stay behind the governed `singularity machine "..."`
    command, which prompts for owner approval — the agent points the user there."""
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
    ]


MACHINE_SYSTEM_PROMPT = (
    "You are the Machine Agent — you manage this machine and, above all, the Claude "
    "Code process, safely.\n"
    "- To find RUNNING Claude Code sessions, call the `find_claude_sessions` tool "
    "(never search for *session* files — that finds config, not the live process).\n"
    "- To inspect the machine, call `detect_machine`.\n"
    "- Consequential operations (install Claude Code, grant permissions, log in) are "
    "governed and owner-approved: tell the user to run `singularity machine \"install "
    "claude code\"` (or the relevant intent), or `singularity claude \"<task>\"` to drive "
    "a governed Claude session. Do not try to install or run arbitrary commands yourself."
)
