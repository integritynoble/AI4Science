"""ai4science chat — persistent REPL session with the configured agent.

Claude Code-style interactive shell: type, get streamed response, type
follow-ups. Conversation state is preserved by ClaudeSDKClient. Tool
use is on by default (matches v0.3 default) — every Edit/Write/Bash
still triggers a confirmation prompt.

Slash commands (handled locally, no LLM call):
  /help, /?         show commands
  /exit, /quit, /q  leave the session
  /clear            clear the terminal
  /files            list context files in the workspace
  /yes              toggle auto-approve for this session
  /readonly         toggle read-only for this session (informational only)
  /cost             show cumulative context usage (if SDK supports it)
  /validate         run `ai4science validate` (deterministic)
  /judge            run `ai4science judge cassi --submission .` (deterministic)
  /status           run `ai4science status` (deterministic)
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ai4science import __version__

console = Console()


def chat(
    agent: str = typer.Option(
        "claude", "--agent", "-a",
        help="Agent provider for the chat session (currently: 'claude').",
    ),
    workspace: Path = typer.Option(
        Path("."), "--workspace", "-w", help="Workspace directory."
    ),
    read_only: bool = typer.Option(
        False, "--read-only", "--readonly",
        help="Disable tool use; agent returns text only.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Auto-approve all tool calls (Edit/Write/Bash) in this session.",
    ),
) -> None:
    """Open a persistent chat session with the agent."""
    if agent.lower() != "claude":
        console.print(
            f"[yellow]Chat mode only supports --agent claude in v0.4.[/yellow]\n"
            f"For Codex, use `codex` directly in your workspace, or use one-shot "
            f"prompt mode: [cyan]ai4science --agent codex \"...\"[/cyan]"
        )
        raise typer.Exit(2)

    # Reuse ClaudeAgent.is_available for the same gate as one-shot mode.
    from ai4science.agents import ClaudeAgent
    probe = ClaudeAgent(read_only=read_only, auto_yes=yes)
    if not probe.is_available():
        console.print(f"[red]Claude agent not available:[/red] {probe.unavailable_reason()}")
        raise typer.Exit(2)

    workspace = workspace.resolve()
    try:
        asyncio.run(_run_chat(workspace=workspace, read_only=read_only, auto_yes=yes))
    except KeyboardInterrupt:
        console.print("\n[dim](Ctrl-C — exiting)[/dim]")
        raise typer.Exit(0)


async def _run_chat(*, workspace: Path, read_only: bool, auto_yes: bool) -> None:
    """Async event loop for the REPL."""
    from claude_agent_sdk import (   # type: ignore
        ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ResultMessage,
    )
    from ai4science.agents.permissions import make_workspace_permission_callback
    from ai4science.prompts import load_system_prompt

    # Build options + permission callback (parallel to claude_agent.py).
    sysprompt_name = "ai4science_system_readonly" if read_only else "ai4science_system"
    system_prompt = load_system_prompt(sysprompt_name)

    if read_only:
        allowed_tools: List[str] = []
        can_use_tool = None
    else:
        allowed_tools = ["Read", "Grep", "Glob", "Edit", "Write", "Bash", "MultiEdit"]
        can_use_tool = make_workspace_permission_callback(workspace, auto_yes=auto_yes)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        permission_mode="default",
        can_use_tool=can_use_tool,
        cwd=str(workspace),
        max_turns=50,   # interactive sessions need plenty of room
    )

    # Initial context: inline existing artifact files so the agent starts
    # with awareness of the workspace state.
    context_files = _workspace_artifacts(workspace)

    async with ClaudeSDKClient(options=options) as client:
        _print_welcome(workspace, read_only, auto_yes, context_files)

        # Send the workspace context as a system-side first message so the
        # agent has it without consuming a user turn. The SDK doesn't have
        # a separate "context inject" API, so we issue a single "/load"-style
        # turn first.
        if context_files:
            seed = (
                "[ai4science] Workspace context for this session:\n\n"
                + _format_files_for_context(context_files, workspace)
                + "\n\nAcknowledge with one short sentence (1–2 words is fine). "
                  "Don't take any action yet — wait for the user's first request."
            )
            await client.query(seed)
            async for msg in client.receive_response():
                pass   # silently consume the acknowledgement

        # Main REPL loop.
        cancel_flag = {"interrupt": False}
        while True:
            try:
                line = await _read_line("ai4science> ")
            except EOFError:
                console.print("\n[dim](Ctrl-D — exiting)[/dim]")
                break
            except KeyboardInterrupt:
                console.print("\n[dim](Ctrl-C — type /exit to quit)[/dim]")
                continue

            line = line.strip()
            if not line:
                continue

            # Slash commands first.
            if line.startswith("/"):
                handled, should_exit = _handle_slash(line, workspace,
                                                     auto_yes=auto_yes,
                                                     read_only=read_only,
                                                     client=client)
                if should_exit:
                    break
                if handled:
                    continue

            # Send to agent + stream response.
            try:
                await client.query(line)
            except Exception as e:
                console.print(f"[red]query error:[/red] {type(e).__name__}: {e}")
                continue

            try:
                await _stream_response(client, cancel_flag)
            except Exception as e:
                console.print(f"[red]stream error:[/red] {type(e).__name__}: {e}")


# ─── helpers ───────────────────────────────────────────────────────────


async def _read_line(prompt: str) -> str:
    """Async-friendly line read. Falls back to stdin pipe when not a tty."""
    loop = asyncio.get_event_loop()
    if not sys.stdin.isatty():
        # In a pipe — read one line, no prompt.
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            raise EOFError
        return line.rstrip("\n")
    # TTY: use input() off the event loop so the SDK can do background work.
    return await loop.run_in_executor(None, lambda: input(prompt))


async def _stream_response(client, cancel_flag: dict) -> None:
    """Iterate `receive_response()` and render text blocks as they arrive."""
    from claude_agent_sdk import (   # type: ignore
        AssistantMessage, ResultMessage,
    )

    first_text = True
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in getattr(msg, "content", []):
                text = getattr(block, "text", None)
                if text:
                    if first_text:
                        console.print()   # blank line before first response
                        first_text = False
                    console.print(text, end="")
            console.print()  # newline after each AssistantMessage
        elif isinstance(msg, ResultMessage):
            # End of this turn. Maybe surface usage on /cost later.
            break


def _handle_slash(line: str, workspace: Path, *, auto_yes: bool,
                  read_only: bool, client) -> tuple[bool, bool]:
    """Return (handled, should_exit)."""
    cmd, _, _arg = line[1:].partition(" ")
    cmd = cmd.lower().strip()

    if cmd in ("exit", "quit", "q"):
        return (True, True)

    if cmd in ("help", "?"):
        _print_help()
        return (True, False)

    if cmd == "clear":
        os.system("clear" if os.name != "nt" else "cls")
        return (True, False)

    if cmd == "files":
        files = _workspace_artifacts(workspace)
        if not files:
            console.print("[dim](no artifact files in this workspace)[/dim]")
        else:
            console.print("[bold]Workspace artifact files:[/bold]")
            for f in files:
                console.print(f"  - {f.relative_to(workspace) if f.is_relative_to(workspace) else f}")
        return (True, False)

    if cmd == "yes":
        console.print("[yellow]Note:[/yellow] /yes toggles need to be set at startup. "
                      "Exit, re-run with `--yes`, and start a new chat.")
        return (True, False)

    if cmd == "readonly":
        console.print("[yellow]Note:[/yellow] read-only mode is set at startup. "
                      "Exit, re-run with `--read-only`, and start a new chat.")
        return (True, False)

    if cmd == "cost":
        try:
            usage = client.get_context_usage()
        except Exception as e:
            console.print(f"[yellow]/cost not available:[/yellow] {e}")
            return (True, False)
        console.print(f"[bold]Context usage:[/bold] {usage}")
        return (True, False)

    if cmd == "validate":
        return _run_local_subcommand("validate", workspace)

    if cmd == "judge":
        return _run_local_subcommand("judge_cassi", workspace)

    if cmd == "status":
        return _run_local_subcommand("status", workspace)

    console.print(f"[yellow]Unknown slash command:[/yellow] /{cmd} "
                  f"(try [cyan]/help[/cyan])")
    return (True, False)


def _run_local_subcommand(name: str, workspace: Path) -> tuple[bool, bool]:
    """Run a deterministic command from inside the REPL without exiting."""
    from ai4science.commands import validate as v, status as s, judge as j
    try:
        if name == "validate":
            v.validate(workspace=workspace)
        elif name == "status":
            s.status(workspace=workspace)
        elif name == "judge_cassi":
            j.cassi(submission=str(workspace))
    except typer.Exit as e:
        if e.exit_code:
            console.print(f"[dim](command exited with code {e.exit_code})[/dim]")
    except Exception as e:
        console.print(f"[red]{name} error:[/red] {type(e).__name__}: {e}")
    return (True, False)


def _print_welcome(workspace: Path, read_only: bool, auto_yes: bool,
                   context_files: List[Path]) -> None:
    mode = "read-only" if read_only else "tool-use"
    yes_note = " + auto-approve" if (auto_yes and not read_only) else ""
    console.print()
    console.print(f"[bold purple]ai4science chat[/bold purple]  v{__version__}")
    console.print(f"  workspace:  [cyan]{workspace}[/cyan]")
    console.print(f"  agent:      claude ({mode}{yes_note})")
    console.print(f"  context:    {len(context_files)} artifact file(s) inlined")
    console.print()
    console.print(
        "[dim]Type a request to chat. Type [/dim][cyan]/help[/cyan][dim] for slash "
        "commands. Press [/dim][cyan]Ctrl-D[/cyan][dim] or type [/dim]"
        "[cyan]/exit[/cyan][dim] to quit.[/dim]"
    )
    console.print()


def _print_help() -> None:
    console.print()
    console.print("[bold]Slash commands:[/bold]")
    rows = [
        ("/help, /?",          "show this list"),
        ("/exit, /quit, /q",   "leave the session"),
        ("/clear",             "clear the terminal"),
        ("/files",             "list workspace artifact files"),
        ("/validate",          "run `ai4science validate` (deterministic)"),
        ("/judge",             "run the CASSI Physics Judge"),
        ("/status",            "show workspace status"),
        ("/cost",              "show context-window usage"),
        ("/yes",               "(info) auto-approve flag is set at startup"),
        ("/readonly",          "(info) read-only flag is set at startup"),
    ]
    width = max(len(r[0]) for r in rows)
    for cmd, descr in rows:
        console.print(f"  [cyan]{cmd:<{width}}[/cyan]   {descr}")
    console.print()


def _workspace_artifacts(workspace: Path) -> List[Path]:
    return [p for p in (
        workspace / "principle.md",
        workspace / "spec.md",
        workspace / "benchmark.md",
        workspace / "solution.md",
    ) if p.exists()]


def _format_files_for_context(files: List[Path], workspace: Path) -> str:
    blobs: List[str] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except Exception as e:
            blobs.append(f"### {f.name} (unreadable: {e})")
            continue
        if len(text) > 8000:
            text = text[:8000] + "\n[... truncated]"
        try:
            rel = f.relative_to(workspace)
        except Exception:
            rel = f
        blobs.append(f"### `{rel}`\n```\n{text}\n```")
    return "\n\n".join(blobs)
