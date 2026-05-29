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
             "Switch live in-session with /model <name>.",
    ),
    continue_session: bool = typer.Option(
        False, "--continue", "-c",
        help="Resume the most recent conversation in this workspace.",
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

    # Reuse ClaudeAgent.is_available for the same gate as one-shot mode.
    from ai4science.agents import ClaudeAgent
    probe = ClaudeAgent(read_only=read_only, auto_yes=yes, plan_mode=plan)
    if not probe.is_available():
        console.print(f"[red]Claude agent not available:[/red] {probe.unavailable_reason()}")
        raise typer.Exit(2)

    workspace = workspace.resolve()
    try:
        asyncio.run(_run_chat(workspace=workspace, read_only=read_only,
                               auto_yes=yes, plan_mode=plan,
                               enable_subagents=not no_subagents,
                               enable_mcp=not no_mcp,
                               continue_session=continue_session,
                               model=model))
    except KeyboardInterrupt:
        console.print("\n[dim](Ctrl-C — exiting)[/dim]")
        raise typer.Exit(0)


async def _run_chat(*, workspace: Path, read_only: bool, auto_yes: bool,
                     plan_mode: bool = False,
                     enable_subagents: bool = True,
                     enable_mcp: bool = True,
                     continue_session: bool = False,
                     model: Optional[str] = None) -> None:
    """Async event loop for the REPL."""
    from claude_agent_sdk import (   # type: ignore
        ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ResultMessage,
    )
    from ai4science.agents.permissions import make_workspace_permission_callback
    from ai4science.agents.subagents import build_pwm_subagents
    from ai4science.agents.mcp_pwm import build_pwm_mcp_server, PWM_MCP_TOOL_NAMES
    from ai4science.memory import augment_system_prompt, find_memory_file
    from ai4science.prompts import load_system_prompt

    # System prompt: plan > read_only > full tool-use.
    if plan_mode:
        sysprompt_name = "ai4science_system_plan"
    elif read_only:
        sysprompt_name = "ai4science_system_readonly"
    else:
        sysprompt_name = "ai4science_system"
    system_prompt = load_system_prompt(sysprompt_name)
    # Project memory (CLAUDE.md / AI4SCIENCE.md / AGENTS.md) — like Claude Code.
    system_prompt = augment_system_prompt(system_prompt, workspace)
    memory_file = find_memory_file(workspace)

    # Capability bundles
    subagents = build_pwm_subagents() if enable_subagents else {}
    pwm_mcp = build_pwm_mcp_server() if enable_mcp else None
    mcp_tool_names = list(PWM_MCP_TOOL_NAMES) if enable_mcp else []

    if plan_mode:
        allowed_tools: List[str] = ["Read", "Grep", "Glob"] + mcp_tool_names
        can_use_tool = None
        permission_mode_initial = "plan"
    elif read_only:
        allowed_tools = []
        can_use_tool = None
        permission_mode_initial = "default"
    else:
        allowed_tools = ["Read", "Grep", "Glob", "Edit", "Write", "Bash",
                         "MultiEdit", "Task"] + mcp_tool_names
        can_use_tool = make_workspace_permission_callback(workspace, auto_yes=auto_yes)
        permission_mode_initial = "default"

    mcp_kw: dict = {"mcp_servers": {"pwm": pwm_mcp}} if pwm_mcp is not None else {}
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        permission_mode=permission_mode_initial,
        can_use_tool=can_use_tool,
        cwd=str(workspace),
        model=model,   # None → the claude CLI default
        max_turns=50,   # interactive sessions need plenty of room
        agents=subagents,
        include_partial_messages=True,   # token-level streaming
        continue_conversation=continue_session,
        **mcp_kw,
    )
    # Track the active model so /model can show + switch it live.
    model_state = {"current": model}

    # Initial context: inline existing artifact files so the agent starts
    # with awareness of the workspace state.
    context_files = _workspace_artifacts(workspace)

    async with ClaudeSDKClient(options=options) as client:
        _print_welcome(workspace, read_only, auto_yes, context_files,
                        plan_mode=plan_mode, memory_file=memory_file,
                        continue_session=continue_session,
                        model=model_state["current"])

        # Seed the workspace context as a first turn — but ONLY for a fresh
        # session. When --continue resumes a prior conversation, re-seeding
        # would re-frame it as new and make the agent forget the carried-over
        # history. The resumed session already has the earlier context.
        if context_files and not continue_session:
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
                line = await _read_line("> ")
            except EOFError:
                console.print("\n[dim](Ctrl-D — exiting)[/dim]")
                break
            except KeyboardInterrupt:
                console.print("\n[dim](Ctrl-C — type /exit to quit)[/dim]")
                continue

            line = line.strip()
            if not line:
                continue

            # Slash commands first — /plan returns the actual user prompt to
            # forward (with plan-mode prefix attached) when a prompt is given;
            # other slash commands handle themselves and skip the LLM.
            single_turn_plan_prompt: Optional[str] = None
            custom_prompt: Optional[str] = None
            if line.startswith("/"):
                # /model [name] — show or switch the model live (like Claude Code).
                _scmd, _, _sarg = line[1:].partition(" ")
                if _scmd.lower() == "model":
                    _sarg = _sarg.strip()
                    if not _sarg:
                        cur = model_state["current"] or "default (your claude CLI default)"
                        console.print(f"[cyan]model:[/cyan] {cur}")
                        console.print("[dim]Switch: /model <name> — e.g. opus, sonnet, "
                                      "haiku, or a full model id[/dim]")
                    else:
                        try:
                            await client.set_model(_sarg)
                            model_state["current"] = _sarg
                            console.print(f"[green]✓ model → {_sarg}[/green]")
                        except Exception as e:
                            console.print(f"[red]could not set model:[/red] "
                                          f"{type(e).__name__}: {e}")
                    continue

                # Custom (user-defined) slash command? Expand + send as a turn.
                from ai4science.commands.custom_commands import (
                    load_custom_commands, expand_command,
                )
                _cmd, _, _carg = line[1:].partition(" ")
                _custom = load_custom_commands(workspace)
                if _cmd.lower() in _custom:
                    custom_prompt = expand_command(_custom[_cmd.lower()], _carg.strip())
                    console.print(f"[dim]/{_cmd.lower()} → custom command "
                                  f"({_custom[_cmd.lower()].name})[/dim]")
                else:
                    handled, should_exit, plan_prompt = _handle_slash(
                        line, workspace,
                        auto_yes=auto_yes, read_only=read_only,
                        plan_mode_active=plan_mode, client=client,
                    )
                    if should_exit:
                        break
                    if plan_prompt is not None:
                        # /plan <prompt> → send under plan mode for ONE turn.
                        single_turn_plan_prompt = plan_prompt
                    elif handled:
                        continue

            # Resolve the outgoing prompt: custom-command expansion, the
            # /plan-extracted prompt, or the original line.
            raw_prompt = custom_prompt or single_turn_plan_prompt or line

            # Expand @-mentions: text files inline; image files become
            # multimodal content blocks (see image_message below).
            from ai4science.agents.mentions import (
                expand_mentions_inline, parse_image_mentions,
            )
            outgoing, attached = expand_mentions_inline(raw_prompt, workspace)
            image_paths = parse_image_mentions(raw_prompt, workspace)
            if attached:
                rels = [str(p.relative_to(workspace.resolve())) for p in attached]
                console.print(f"[dim]📎 attached: {', '.join(rels)}[/dim]")

            # Build a multimodal message when images are attached.
            image_message = None
            if image_paths:
                from ai4science.agents.images import build_user_message
                try:
                    image_message = build_user_message(outgoing, image_paths)
                except ValueError as e:
                    console.print(f"[yellow]image not attached:[/yellow] {e}")
                    image_message = None

            # Plan-mode toggle for this turn only.
            if single_turn_plan_prompt is not None and not plan_mode:
                try:
                    client.set_permission_mode("plan")
                except Exception:
                    pass
                outgoing = (
                    "[Plan mode for this turn]\n\n"
                    "Use Read/Grep/Glob to investigate, then return a structured "
                    "plan with concrete file paths and actions. Do NOT edit any "
                    "files — the user will review your plan and re-issue if they "
                    "want execution.\n\n"
                    "## Request\n\n"
                    + outgoing
                )

            # Send to agent + stream response. Structured multimodal message
            # (text + images) goes via the streaming-input path; otherwise a
            # plain string.
            try:
                if image_message is not None:
                    from ai4science.agents.images import single_message_stream
                    await client.query(single_message_stream(image_message))
                else:
                    await client.query(outgoing)
            except Exception as e:
                console.print(f"[red]query error:[/red] {type(e).__name__}: {e}")
                if single_turn_plan_prompt is not None and not plan_mode:
                    try:
                        client.set_permission_mode("default")
                    except Exception:
                        pass
                continue

            try:
                await _stream_response(client, cancel_flag)
            except Exception as e:
                console.print(f"[red]stream error:[/red] {type(e).__name__}: {e}")
            finally:
                # Restore default permission mode after a single-turn /plan.
                if single_turn_plan_prompt is not None and not plan_mode:
                    try:
                        client.set_permission_mode("default")
                    except Exception:
                        pass


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


async def _render_live(msgs) -> None:
    """TTY renderer: live-updating markdown + inline tool lines."""
    from claude_agent_sdk import (   # type: ignore
        AssistantMessage, UserMessage, ResultMessage, StreamEvent,
        TextBlock, ToolUseBlock, ToolResultBlock,
    )
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.console import Group
    from rich.text import Text
    from ai4science.agents.streaming import (
        extract_text_delta, format_tool_use, format_tool_result,
    )

    segments: list = []
    current: list[str] = []
    streamed_any = False

    def render():
        parts = list(segments)
        if current:
            parts.append(Markdown("".join(current)))
        return Group(*parts) if parts else Text("")

    def flush_text():
        nonlocal current
        if current:
            segments.append(Markdown("".join(current)))
            current = []

    console.print()
    with Live(render(), console=console, refresh_per_second=12,
              vertical_overflow="visible") as live:
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
                break
        flush_text()
        live.update(render())


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
            break
    newline_if_needed()


def _handle_slash(line: str, workspace: Path, *, auto_yes: bool,
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
            client.set_permission_mode("acceptEdits")
            console.print("[green]✓ accept-edits ON[/green] — Edit/Write/Bash auto-approved "
                          "this session. Use [cyan]/default[/cyan] to require confirmation again.")
        except Exception as e:
            console.print(f"[yellow]/yes not available:[/yellow] {e}")
        return (True, False, None)

    if cmd in ("readonly", "read-only"):
        # Live toggle to read-only (plan permission mode — no edits).
        try:
            client.set_permission_mode("plan")
            console.print("[green]✓ read-only ON[/green] — no edits this session "
                          "(Read/Grep/Glob only). Use [cyan]/default[/cyan] to restore editing.")
        except Exception as e:
            console.print(f"[yellow]/readonly not available:[/yellow] {e}")
        return (True, False, None)

    if cmd in ("default", "normal", "edit"):
        # Restore the default mode: edits allowed, each confirmed.
        try:
            client.set_permission_mode("default")
            console.print("[green]✓ default mode[/green] — edits allowed, each prompts "
                          "for confirmation.")
        except Exception as e:
            console.print(f"[yellow]/default not available:[/yellow] {e}")
        return (True, False, None)

    if cmd == "cost":
        try:
            usage = client.get_context_usage()
        except Exception as e:
            console.print(f"[yellow]/cost not available:[/yellow] {e}")
            return (True, False, None)
        console.print(f"[bold]Context usage:[/bold] {usage}")
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
                   model: Optional[str] = None) -> None:
    if plan_mode:
        mode = "plan"
    elif read_only:
        mode = "read-only"
    else:
        mode = "tool-use"
    yes_note = " + auto-approve" if (auto_yes and not read_only and not plan_mode) else ""
    console.print()
    console.print(f"[bold purple]ai4science chat[/bold purple]  v{__version__}")
    console.print(f"  workspace:  [cyan]{workspace}[/cyan]")
    console.print(f"  agent:      claude ({mode}{yes_note})")
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
        ("/model [name]",      "show or switch the model live (opus, sonnet, haiku, or id)"),
        ("/validate",          "run `ai4science validate` (deterministic)"),
        ("/judge",             "run the CASSI Physics Judge"),
        ("/status",            "show workspace status"),
        ("/cost",              "show context-window usage"),
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
