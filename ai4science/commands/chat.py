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
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ai4science import __version__
from ai4science.harness.agents import registry as agent_registry
from ai4science.harness.repl import run_common_repl

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
    plan: bool = typer.Option(
        False, "--plan",
        help="Whole-session plan mode: no edits, agent produces plans only. "
             "Use the in-REPL /plan command for single-turn plan mode.",
    ),
    no_subagents: bool = typer.Option(
        False, "--no-subagents",
        help="Disable PWM sub-agent delegation (physics-reviewer, "
             "schema-validator, benchmark-architect).",
    ),
    no_mcp: bool = typer.Option(
        False, "--no-mcp",
        help="Disable the in-process PWM MCP tools (pwm_validate, "
             "pwm_judge_cassi, pwm_status, pwm_lookup_artifact).",
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m",
        help="Model for the session (e.g. opus, sonnet, haiku, or a full id). "
             "Defaults to AI4SCIENCE_MODEL, else your claude CLI default. "
             "In-session, type /model to pick from a menu.",
    ),
    backend: Optional[str] = typer.Option(
        None, "--backend", "-b",
        help="LLM backend: anthropic | openai | gemini | deepseek | qwen. "
             "If omitted it is inferred from --model, else auto-detected. "
             "In-session, type /model <backend> to switch.",
    ),
    continue_session: bool = typer.Option(
        False, "--continue", "-c",
        help="Resume the most recent conversation in this workspace.",
    ),
    resume: Optional[str] = typer.Option(
        None, "--resume",
        help="Resume a SPECIFIC past session by id. List ids with the in-REPL "
             "/resume command (or /sessions).",
    ),
    mode: Optional[str] = typer.Option(
        None, "--mode",
        help="Session mode: 'unified-LLM' (general assistant across Claude/ChatGPT/Gemini; "
             "'common' is an alias), 'research', 'paper', 'claude code', 'codex', or a "
             "'specific' domain agent. Defaults to AI4SCIENCE_MODE, else unified-LLM. "
             "Switch live with /mode.",
    ),
) -> None:
    """Open a persistent chat session with the agent."""
    import os
    model = model or os.environ.get("AI4SCIENCE_MODEL")
    if agent.lower() != "claude":
        console.print(
            f"[yellow]Chat mode only supports --agent claude in v0.4.[/yellow]\n"
            f"For Codex, use `codex` directly in your workspace, or use one-shot "
            f"prompt mode: [cyan]ai4science --agent codex \"...\"[/cyan]"
        )
        raise typer.Exit(2)

    workspace = workspace.resolve()

    # Resolve --mode against the agent registry. The active AgentSpec drives the
    # session (registry + system prompt) inside run_common_repl; here we only pass
    # mode_label and the spec's prompt as a harmless fallback.
    mode = (mode or os.environ.get("AI4SCIENCE_MODE") or "unified-LLM").lower()
    backend = backend or os.environ.get("AI4SCIENCE_BACKEND")
    spec = agent_registry.get(mode)
    if spec is None:
        names = ", ".join(sorted(agent_registry.AGENT_REGISTRY))
        console.print(f"[yellow]Unknown --mode {mode!r}; using 'unified-LLM'. "
                      f"Available: {names}[/yellow]")
        spec = agent_registry.get("unified-LLM")

    from ai4science.harness import persistence
    resume_hist = None
    sid = resume
    if resume:
        resume_hist = persistence.load(resume)
    elif continue_session:
        sid = persistence.most_recent(workspace)
        resume_hist = persistence.load(sid) if sid else None

    try:
        run_common_repl(
            workspace,
            read_only=read_only or plan,
            auto_yes=yes,
            backend=backend,
            model=model,
            resume_history=resume_hist,
            session_id=sid,
            system_prompt=spec.system_prompt,
            mode_label=spec.name,
        )
    except KeyboardInterrupt:
        console.print("\n[dim](Ctrl-C — exiting)[/dim]")
        raise typer.Exit(0)
    return


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
    """Stream the response with inline tool-call visibility.

    Renders differently by output target:
      - TTY  → live-updating rich.Markdown (token streaming, pretty).
      - non-TTY (piped / CI / scripted) → plain incremental prints. The
        Live renderer's frame redraws can drop earlier output when several
        turns render back-to-back into a pipe, so we avoid Live there.
    """
    msgs = client.receive_response()
    if sys.stdout.isatty():
        await _render_live(msgs)
    else:
        await _render_plain(msgs, console)


# Whimsical "working" words for the thinking spinner (like Claude Code).
WHIMSY = (
    "Tomfoolering", "Razzmatazzing", "Proofing", "Sautéing", "Frolicking",
    "Noodling", "Percolating", "Conjuring", "Marinating", "Simmering",
    "Finagling", "Schlepping", "Bamboozling", "Cogitating", "Ruminating",
    "Galvanizing", "Concocting", "Synthesizing", "Whirring", "Pondering",
    "Scheming", "Brewing", "Tinkering", "Wrangling", "Mulling", "Vibing",
)


def _fmt_tokens(n) -> str:
    if not n:
        return "0"
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def _result_usage(msg) -> dict:
    """Pull input/output token counts from a ResultMessage, defensively.

    The 'input' side sums fresh + cached input so it reflects everything the
    model actually saw (closer to Claude Code's number), not just the small
    non-cached delta."""
    u = getattr(msg, "usage", None)
    if isinstance(u, dict):
        inp = ((u.get("input_tokens") or 0)
               + (u.get("cache_read_input_tokens") or 0)
               + (u.get("cache_creation_input_tokens") or 0))
        return {"input": inp or None, "output": u.get("output_tokens")}
    return {}


async def _render_live(msgs) -> None:
    """TTY renderer: a whimsy 'working' spinner, then live markdown + tool lines,
    then a footer with elapsed time + token usage (Claude Code-style)."""
    import random
    import time as _time
    from claude_agent_sdk import (   # type: ignore
        AssistantMessage, UserMessage, ResultMessage, StreamEvent,
        TextBlock, ToolUseBlock, ToolResultBlock,
    )
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.console import Group
    from rich.text import Text
    from rich.spinner import Spinner
    from ai4science.agents.streaming import (
        extract_text_delta, format_tool_use, format_tool_result,
    )

    word = random.choice(WHIMSY)
    start = _time.monotonic()
    segments: list = []
    current: list[str] = []
    streamed_any = False
    usage: dict = {}

    def render():
        parts = list(segments)
        if current:
            parts.append(Markdown("".join(current)))
        if parts:
            return Group(*parts)
        # Nothing yet → whimsy spinner + a live elapsed timer.
        el = int(_time.monotonic() - start)
        return Spinner("dots", text=Text.from_markup(
            f"[magenta]{word}…[/magenta] [dim]({el}s · esc to interrupt)[/dim]"))

    def flush_text():
        nonlocal current
        if current:
            segments.append(Markdown("".join(current)))
            current = []

    console.print()
    with Live(render(), console=console, refresh_per_second=12,
              vertical_overflow="visible") as live:
        # Background ticker: keep the spinner's timer moving even while the
        # agent is thinking and no messages are arriving.
        async def _tick():
            try:
                while True:
                    await asyncio.sleep(0.4)
                    if not segments and not current:
                        live.update(render())
            except asyncio.CancelledError:
                pass
        ticker = asyncio.create_task(_tick())
        try:
            async for msg in msgs:
                if isinstance(msg, StreamEvent):
                    delta = extract_text_delta(getattr(msg, "event", None))
                    if delta:
                        current.append(delta)
                        streamed_any = True
                        live.update(render())
                elif isinstance(msg, AssistantMessage):
                    for block in getattr(msg, "content", []):
                        if isinstance(block, ToolUseBlock):
                            flush_text()
                            segments.append(Text.from_markup(
                                format_tool_use(block.name, block.input)))
                            live.update(render())
                        elif isinstance(block, TextBlock):
                            if not streamed_any and not current:
                                current.append(block.text)
                                live.update(render())
                elif isinstance(msg, UserMessage):
                    for block in getattr(msg, "content", []):
                        if isinstance(block, ToolResultBlock):
                            flush_text()
                            segments.append(Text.from_markup(format_tool_result(
                                block.content, getattr(block, "is_error", False))))
                            live.update(render())
                elif isinstance(msg, ResultMessage):
                    usage = _result_usage(msg)
                    break
            flush_text()
            live.update(render())
        finally:
            ticker.cancel()

    # Footer: whimsy word · elapsed · token usage (like Claude Code's status).
    el = _time.monotonic() - start
    foot = f"[dim]✓ {word.lower()} · {el:.1f}s"
    if usage.get("input") or usage.get("output"):
        foot += (f" · ↑{_fmt_tokens(usage.get('input'))} "
                 f"↓{_fmt_tokens(usage.get('output'))} tokens")
    foot += "[/dim]"
    console.print(foot)


async def _render_plain(msgs, out_console) -> None:
    """Non-TTY renderer: incremental plain prints, no rich.Live.

    Streams text deltas as they arrive and prints each tool call / result
    on its own line. Nothing is overwritten, so it captures cleanly when
    piped to a file or another process.
    """
    from claude_agent_sdk import (   # type: ignore
        AssistantMessage, UserMessage, ResultMessage, StreamEvent,
        TextBlock, ToolUseBlock, ToolResultBlock,
    )
    from rich.text import Text
    from ai4science.agents.streaming import (
        extract_text_delta, format_tool_use, format_tool_result,
    )

    import random
    import time as _time
    word = random.choice(WHIMSY)
    start = _time.monotonic()
    usage: dict = {}
    streamed_any = False
    mid_line = False   # True when the last thing written didn't end in \n

    def newline_if_needed():
        nonlocal mid_line
        if mid_line:
            out_console.file.write("\n")
            out_console.file.flush()
            mid_line = False

    async for msg in msgs:
        if isinstance(msg, StreamEvent):
            delta = extract_text_delta(getattr(msg, "event", None))
            if delta:
                out_console.file.write(delta)
                out_console.file.flush()
                streamed_any = True
                mid_line = not delta.endswith("\n")
        elif isinstance(msg, AssistantMessage):
            for block in getattr(msg, "content", []):
                if isinstance(block, ToolUseBlock):
                    newline_if_needed()
                    out_console.print(Text.from_markup(
                        format_tool_use(block.name, block.input)))
                elif isinstance(block, TextBlock):
                    if not streamed_any:
                        newline_if_needed()
                        out_console.print(block.text)
        elif isinstance(msg, UserMessage):
            for block in getattr(msg, "content", []):
                if isinstance(block, ToolResultBlock):
                    newline_if_needed()
                    out_console.print(Text.from_markup(format_tool_result(
                        block.content, getattr(block, "is_error", False))))
        elif isinstance(msg, ResultMessage):
            usage = _result_usage(msg)
            break
    newline_if_needed()
    el = _time.monotonic() - start
    foot = f"[dim]✓ {word.lower()} · {el:.1f}s"
    if usage.get("input") or usage.get("output"):
        foot += (f" · ↑{_fmt_tokens(usage.get('input'))} "
                 f"↓{_fmt_tokens(usage.get('output'))} tokens")
    foot += "[/dim]"
    out_console.print(foot)


async def _handle_slash(line: str, workspace: Path, *, auto_yes: bool,
                        read_only: bool, client,
                        plan_mode_active: bool = False
                        ) -> tuple[bool, bool, Optional[str]]:
    """Return (handled, should_exit, plan_prompt_to_forward).

    If the third element is non-None, it means the user typed
    ``/plan <prompt>`` — the caller should forward that prompt under
    plan-mode framing for a single turn.
    """
    cmd, _, _arg = line[1:].partition(" ")
    cmd = cmd.lower().strip()
    arg = _arg.strip()

    if cmd in ("exit", "quit", "q"):
        return (True, True, None)

    if cmd in ("help", "?"):
        _print_help()
        return (True, False, None)

    if cmd == "clear":
        os.system("clear" if os.name != "nt" else "cls")
        return (True, False, None)

    if cmd == "plan":
        if not arg:
            console.print(
                "[bold]/plan <your request>[/bold] — run the next request in "
                "plan mode (read-only; agent produces a plan). "
                "For a whole-session plan, exit and re-launch with "
                "[cyan]ai4science chat --plan[/cyan]."
            )
            return (True, False, None)
        if plan_mode_active or read_only:
            # Already restricted; just forward the prompt as-is via normal flow.
            console.print("[dim](already in plan/read-only mode — sending request normally)[/dim]")
            return (True, False, arg)
        return (True, False, arg)

    if cmd == "files":
        files = _workspace_artifacts(workspace)
        if not files:
            console.print("[dim](no artifact files in this workspace)[/dim]")
        else:
            console.print("[bold]Workspace artifact files:[/bold]")
            for f in files:
                console.print(f"  - {f.relative_to(workspace) if f.is_relative_to(workspace) else f}")
        return (True, False, None)

    if cmd == "commands":
        from ai4science.commands.custom_commands import load_custom_commands
        custom = load_custom_commands(workspace)
        if not custom:
            console.print("[dim]No custom commands. Add `<name>.md` files under "
                          ".ai4science/commands/ or ~/.config/ai4science/commands/.[/dim]")
        else:
            console.print("[bold]Custom slash commands:[/bold]")
            for name, path in sorted(custom.items()):
                console.print(f"  [cyan]/{name}[/cyan]  [dim]({path})[/dim]")
        return (True, False, None)

    if cmd in ("yes", "acceptedits", "accept-edits"):
        # Live toggle to auto-accept edits (like Claude Code's accept-edits mode).
        try:
            await client.set_permission_mode("acceptEdits")
            console.print("[green]✓ accept-edits ON[/green] — Edit/Write/Bash auto-approved "
                          "this session. Use [cyan]/default[/cyan] to require confirmation again.")
        except Exception as e:
            console.print(f"[yellow]/yes not available:[/yellow] {e}")
        return (True, False, None)

    if cmd in ("readonly", "read-only"):
        # Live toggle to read-only (plan permission mode — no edits).
        try:
            await client.set_permission_mode("plan")
            console.print("[green]✓ read-only ON[/green] — no edits this session "
                          "(Read/Grep/Glob only). Use [cyan]/default[/cyan] to restore editing.")
        except Exception as e:
            console.print(f"[yellow]/readonly not available:[/yellow] {e}")
        return (True, False, None)

    if cmd in ("default", "normal", "edit"):
        # Restore the default mode: edits allowed, each confirmed.
        try:
            await client.set_permission_mode("default")
            console.print("[green]✓ default mode[/green] — edits allowed, each prompts "
                          "for confirmation.")
        except Exception as e:
            console.print(f"[yellow]/default not available:[/yellow] {e}")
        return (True, False, None)

    if cmd == "cost":
        try:
            usage = await client.get_context_usage()
        except Exception as e:
            console.print(f"[yellow]/cost not available:[/yellow] {e}")
            return (True, False, None)
        console.print(_format_context_usage(usage))
        return (True, False, None)

    if cmd == "validate":
        return _run_local_subcommand("validate", workspace)

    if cmd == "judge":
        return _run_local_subcommand("judge_cassi", workspace)

    if cmd == "status":
        return _run_local_subcommand("status", workspace)

    console.print(f"[yellow]Unknown slash command:[/yellow] /{cmd} "
                  f"(try [cyan]/help[/cyan])")
    return (True, False, None)


def _run_local_subcommand(name: str, workspace: Path) -> tuple[bool, bool, Optional[str]]:
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
    return (True, False, None)


def _print_welcome(workspace: Path, read_only: bool, auto_yes: bool,
                   context_files: List[Path], plan_mode: bool = False,
                   memory_file: Optional[Path] = None,
                   continue_session: bool = False,
                   model: Optional[str] = None,
                   session_mode: str = "unified-LLM") -> None:
    if plan_mode:
        toolmode = "plan"
    elif read_only:
        toolmode = "read-only"
    else:
        toolmode = "tool-use"
    yes_note = " + auto-approve" if (auto_yes and not read_only and not plan_mode) else ""
    console.print()
    console.print(f"[bold purple]ai4science chat[/bold purple]  v{__version__}")
    console.print(f"  workspace:  [cyan]{workspace}[/cyan]")
    console.print(f"  agent:      claude ({toolmode}{yes_note})")
    console.print(f"  mode:       {session_mode}  [dim](/mode to change)[/dim]")
    console.print(f"  model:      {model or 'default'}  [dim](/model to change)[/dim]")
    console.print(f"  context:    {len(context_files)} artifact file(s) inlined")
    if memory_file is not None:
        console.print(f"  memory:     [green]{memory_file.name}[/green] loaded")
    if continue_session:
        console.print(f"  session:    [yellow]resuming previous conversation[/yellow]")
    console.print()
    console.print(
        "[dim]Type a request to chat. Type [/dim][cyan]/help[/cyan][dim] for slash "
        "commands. Press [/dim][cyan]Ctrl-D[/cyan][dim] or type [/dim]"
        "[cyan]/exit[/cyan][dim] to quit.[/dim]"
    )
    console.print()


def _list_sessions(workspace: Path) -> None:
    """List this workspace's past chat sessions (id + summary + when)."""
    try:
        from claude_agent_sdk import list_sessions  # type: ignore
    except Exception as e:
        console.print(f"[yellow]/resume not available:[/yellow] {e}")
        return
    try:
        sessions = list_sessions(directory=str(workspace), limit=15)
    except Exception as e:
        console.print(f"[yellow]could not list sessions:[/yellow] {type(e).__name__}: {e}")
        return
    if not sessions:
        console.print("[dim]No past sessions for this workspace yet.[/dim]")
        return
    console.print("[bold]Past sessions (newest first):[/bold]")
    for s in sessions:
        sid = getattr(s, "session_id", "?")
        summary = (getattr(s, "summary", "") or "").strip().replace("\n", " ")
        if len(summary) > 64:
            summary = summary[:61] + "..."
        when = getattr(s, "last_modified", "")
        console.print(f"  [cyan]{sid}[/cyan]  [dim]{when}[/dim]  {summary}")
    console.print("[dim]Resume one: exit, then "
                  "[cyan]ai4science --resume <id>[/cyan] "
                  "(or [cyan]ai4science --continue[/cyan] for the most recent)[/dim]")


def _format_context_usage(usage) -> str:
    """One-line context summary from the SDK's get_context_usage() dict.

    Falls back to repr only if the expected fields are missing, so a schema
    change degrades gracefully rather than dumping the raw nested structure.
    """
    if not isinstance(usage, dict):
        return f"[bold]Context:[/bold] {usage}"
    used = usage.get("totalTokens")
    cap = usage.get("maxTokens")
    pct = usage.get("percentage")
    if used is None or cap is None:
        return f"[bold]Context:[/bold] {usage}"
    line = f"[bold]Context:[/bold] {used:,} / {cap:,} tokens"
    if pct is not None:
        line += f" ([cyan]{pct}%[/cyan])"
    thr = usage.get("autoCompactThreshold")
    if thr and usage.get("isAutoCompactEnabled"):
        line += f"  [dim]· auto-compacts at {thr:,}[/dim]"
    return line


async def _do_compact(client) -> None:
    """Report context usage. Manual compaction is not exposed by the SDK —
    the claude CLI auto-compacts the live window (PreCompact hook). For a hard
    reset, /exit and relaunch with --continue (the compacted history carries)."""
    try:
        usage = await client.get_context_usage()
        console.print(_format_context_usage(usage))
    except Exception as e:
        console.print(f"[dim](context usage unavailable: {e})[/dim]")
    console.print("[dim]The claude CLI auto-compacts the context window as it "
                  "fills (no manual trigger needed). For a hard reset now, /exit "
                  "and relaunch with [cyan]--continue[/cyan].[/dim]")


def _print_help() -> None:
    console.print()
    console.print("[bold]Slash commands:[/bold]")
    rows = [
        ("/help, /?",          "show this list"),
        ("/exit, /quit, /q",   "leave the session"),
        ("/clear",             "clear the terminal"),
        ("/files",             "list workspace artifact files"),
        ("/commands",          "list custom (user-defined) slash commands"),
        ("/plan <request>",    "single-turn plan mode (no edits, agent returns a plan)"),
        ("/mode",              "switch mode: unified-LLM / research / paper / claude code / codex / specific"),
        ("/model",             "pick the model from a menu (or /model <name> to switch directly)"),
        ("/validate",          "run `ai4science validate` (deterministic)"),
        ("/judge",             "run the CASSI Physics Judge"),
        ("/status",            "show workspace status"),
        ("/cost",              "show context-window usage"),
        ("/compact",           "context usage + compaction state (CLI auto-compacts)"),
        ("/model [name]",      "show or switch the model live (opus/sonnet/haiku)"),
        ("/resume, /sessions", "list past sessions to relaunch with --resume <id>"),
        ("/yes",               "auto-approve edits this session (accept-edits mode)"),
        ("/readonly",          "switch to read-only this session (no edits)"),
        ("/default",           "restore default mode (edits allowed, each confirmed)"),
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
