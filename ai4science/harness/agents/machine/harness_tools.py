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


def _denied_via_telegram(action: str, detail: str, request_id: str) -> bool:
    """True if Telegram is configured AND the owner denied (or it timed out) —
    the action must NOT run. False means proceed: either the owner approved on
    Telegram, or Telegram isn't configured and the REPL already gated locally."""
    from ai4science.harness.agents.machine.telegram import owner_gate
    return owner_gate(action, detail, request_id=request_id) is False


def _resolve(session):
    """Turn a name-or-pid into a pid, or None if no such session."""
    from ai4science.harness.agents.machine.supervisor import resolve_pid
    return resolve_pid(session)


def _stop_claude_session(workspace, session) -> str:
    from ai4science.harness.agents.machine.sessions import stop_session
    pid = _resolve(session)
    if pid is None:
        return f"No session '{session}' — run `session ls` (or find_claude_sessions) for names and pids."
    if _denied_via_telegram("STOP (SIGTERM) a running Claude Code session",
                            f"session '{session}' (pid {pid})", f"stop-{pid}"):
        return f"Owner denied via Telegram — session '{session}' (pid {pid}) was NOT stopped."
    r = stop_session(pid)
    if r["ok"]:
        return f"Sent SIGTERM to session '{session}' (pid {r['pid']}) — {r['note']}."
    return f"Could not stop '{session}' (pid {pid}): {r['reason']}."


def _govern_claude_session(workspace, session, ceiling="A1") -> str:
    from ai4science.harness.agents.machine.sessions import govern_session
    pid = _resolve(session)
    if pid is None:
        return f"No session '{session}' — run `session ls` (or find_claude_sessions) for names and pids."
    if _denied_via_telegram(f"GOVERN (wire the hook @ {ceiling}) a running Claude Code session",
                            f"session '{session}' (pid {pid})", f"govern-{pid}"):
        return f"Owner denied via Telegram — session '{session}' (pid {pid}) was NOT governed."
    r = govern_session(pid, ceiling=ceiling)
    if r["ok"]:
        return (f"Adopted session '{r.get('name')}' @ {r['ceiling']} in {r['project_dir']}. "
                f"{r['note']}")
    return f"Could not govern '{session}' (pid {pid}): {r['reason']}."


def _send_to_session(workspace, session, text=None, key=None, enter=True) -> str:
    from ai4science.harness.agents.machine.sessions import send_to_session
    r = send_to_session(session, text=text, key=key, enter=bool(enter))
    if r["ok"]:
        return f"Sent to session '{session}' (tmux {r['target']}): {r['sent'] or '⏎'}"
    return f"Could not send to '{session}': {r['reason']}"


def machine_tools(ctx) -> list:
    """Machine operations as tools. Read-only discovery (find_claude_sessions /
    detect_machine) plus two owner-gated actions on a running session —
    govern_claude_session and stop_claude_session (mutating=True → the REPL asks
    the owner before they run). Install / permission / login stay behind the
    governed `singularity machine "..."` command; the agent points the user there."""
    # When Telegram is configured, stop/govern approve on the phone (inside the
    # tool). Mark them non-mutating so the REPL's local gate doesn't ALSO prompt;
    # without Telegram they stay mutating so the REPL prompts the owner locally.
    from ai4science.harness.agents.machine.telegram import telegram_config
    local_gate = telegram_config() is None
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
            description=("Adopt a RUNNING Claude session (by name or pid, from find_claude_sessions): "
                         "attach a durable supervisor + wire the governance hook into its project "
                         "dir. Takes effect on the next/restarted session there — one already "
                         "running must be restarted to pick it up. Owner-approved."),
            parameters={"type": "object", "properties": {
                "session": {"type": "string", "description": "name or pid of the Claude session"},
                "ceiling": {"type": "string", "enum": ["A0", "A1", "A2"],
                            "description": "capability ceiling to enforce (default A1)"},
            }, "required": ["session"]},
            func=_govern_claude_session, mutating=local_gate,
        ),
        Tool(
            name="stop_claude_session",
            description=("Stop (terminate, SIGTERM) a RUNNING Claude session by name or pid — for a "
                         "runaway. Only sessions you own. Consequential and owner-approved: use "
                         "only when asked to stop/kill a session."),
            parameters={"type": "object", "properties": {
                "session": {"type": "string", "description": "name or pid of the Claude session"},
            }, "required": ["session"]},
            func=_stop_claude_session, mutating=local_gate,
        ),
        Tool(
            name="send_to_session",
            description=("Type keystrokes into a RUNNING, tmux-hosted Claude session (by name or "
                         "pid) — answer its native permission prompt (e.g. send \"1\" for Yes), or "
                         "give it a task to type. tmux-only (a bare terminal can't be driven). "
                         "Owner-approved. Use this to OPERATE a live interactive session."),
            parameters={"type": "object", "properties": {
                "session": {"type": "string", "description": "name or pid of the tmux session"},
                "text": {"type": "string", "description": "text to type (e.g. \"1\", or a task)"},
                "key": {"type": "string", "description": "a named key instead of/after text: Enter, Escape, C-c"},
                "enter": {"type": "boolean", "description": "press Enter after the text (default true)"},
            }, "required": ["session"]},
            func=_send_to_session, mutating=local_gate,
        ),
    ]


MACHINE_SYSTEM_PROMPT = (
    "You are the Machine Agent — you manage this machine and, above all, the Claude "
    "Code process, safely.\n"
    "- To find RUNNING Claude Code sessions, call the `find_claude_sessions` tool "
    "(never search for *session* files — that finds config, not the live process).\n"
    "- Sessions are addressed by NAME (find_claude_sessions lists each session's name "
    "beside its pid); a pid also works anywhere a name does.\n"
    "- Each session comes with a short INTRODUCTION (project/repo + branch, interactive "
    "vs. its headless task, how long it's been running). When the user is choosing a "
    "session, show these intros so they can recognize which one they mean.\n"
    "- To act on a running session, first `find_claude_sessions`, then:\n"
    "  • `govern_claude_session(session)` to adopt it (supervisor + hook) — this takes "
    "effect on the next/restarted session there; tell the user the running one must be "
    "restarted to be governed.\n"
    "  • `stop_claude_session(session)` to terminate a runaway (only sessions the user owns). Use "
    "stop only when the user asks to stop/kill a session — both are owner-approved before they run.\n"
    "  • `send_to_session(session, text=..., key=...)` to OPERATE a live tmux-hosted session — type "
    "into it or answer its prompt (e.g. text=\"1\" to answer Yes). Only works if the session runs in "
    "tmux; if it reports 'not in tmux', tell the user to start it with `tmux new -s <name> claude`.\n"
    "- To inspect the machine, call `detect_machine`.\n"
    "- Consequential operations (install Claude Code, grant permissions, log in) are "
    "governed and owner-approved: tell the user to run `singularity machine \"install "
    "claude code\"` (or the relevant intent), or `singularity claude \"<task>\"` to drive "
    "a governed Claude session. Do not try to install or run arbitrary commands yourself."
)
