"""ai4science — session-style CLI for Physics World Model contributions.

Two surfaces:

1. **Subcommand mode** (deterministic):
       ai4science init <name>
       ai4science contribute <type>
       ai4science validate
       ai4science judge cassi --submission .
       ai4science overseer review --submission .
       ai4science package
       ai4science submit --dry-run

2. **Prompt-first mode** (one-shot):
       ai4science --agent claude "Help me draft a CASSI spec"
       ai4science --agent none "Validate my PWM contribution"

   The router first tries rule-based intent detection (free, deterministic).
   If nothing matches and --agent is claude/codex AND is_available(), it
   hands the prompt off to the selected agent provider for an LLM call.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ai4science import __version__
from ai4science.agents import get_agent
from ai4science.commands import (
    init as init_cmd,
    contribute as contribute_cmd,
    validate as validate_cmd,
    judge as judge_cmd,
    overseer as overseer_cmd,
    package as package_cmd,
    submit as submit_cmd,
    status as status_cmd,
    chat as chat_cmd,
)

console = Console()

# Module-level state for the agent the user selected via --agent. We thread
# it through sys.argv parsing because Typer's no_args_is_help wraps the app
# in a way that doesn't naturally compose with our prompt-first dispatcher.
_SELECTED_AGENT: Optional[str] = None


app = typer.Typer(
    name="ai4science",
    help=(
        "AI4Science — session-style CLI for Physics World Model contributions.\n"
        "Run with a subcommand (init, contribute, validate, judge, overseer, package, "
        "submit, status) OR with a free-form English prompt in quotes."
    ),
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    add_completion=False,
)


# ─── Subcommands ───────────────────────────────────────────────────────


app.add_typer(contribute_cmd.app, name="contribute",
              help="Create a Principle / Spec / Benchmark / Solution from the template.")
app.add_typer(judge_cmd.app, name="judge",
              help="Run the deterministic Physics Judge on a submission.")
app.add_typer(overseer_cmd.app, name="overseer",
              help="Local Overseer review combining validate + judge + claim checks.")

# Single-command leaves
app.command("init", help="Create a new contribution workspace.")(init_cmd.init)
app.command("validate", help="Validate YAML front matter and required fields.")(validate_cmd.validate)
app.command("package", help="Package the submission and generate hashes.")(package_cmd.package)
app.command("submit", help="Submit (dry-run for v0.1).")(submit_cmd.submit)
app.command("status", help="Show local workspace status.")(status_cmd.status)
app.command("chat", help="Open a persistent REPL chat session with the agent.")(chat_cmd.chat)


@app.command("version", help="Print the AI4Science CLI version.")
def version_cmd() -> None:
    console.print(f"ai4science {__version__}")


@app.command("agents", help="List configured agent providers and their availability.")
def agents_cmd() -> None:
    """Report on each known agent provider's availability + auth hint."""
    from rich.table import Table
    table = Table(title="Agent providers", show_lines=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Available")
    table.add_column("Notes")
    for name in ("none", "claude", "codex"):
        agent = get_agent(name)
        ok = agent.is_available()
        notes = getattr(agent, "unavailable_reason", lambda: "")()
        table.add_row(name, "[green]yes[/green]" if ok else "[yellow]no[/yellow]", notes)
    console.print(table)


# ─── Prompt-first dispatch ─────────────────────────────────────────────


# Routing splits into UTILITY intents (always rule-dispatched — no LLM is
# useful for `validate`, `judge`, `package`, etc.) and DRAFTING intents
# (rule-dispatched only when --agent=none; routed to the agent otherwise,
# because that's why the user picked an agent).
#
# The v0.1 bug was that "draft a CASSI principle" matched "cassi" → judge_cassi.
# Two structural fixes here:
#   1. Split utility (always deterministic) from drafting (LLM if available)
#   2. Inside each tier, verbs and explicit artifact nouns rank above
#      domain keywords like "cassi"


def _route_utility(prompt: str) -> Optional[str]:
    """Match prompts that should ALWAYS run a deterministic command, even
    when an agent is selected (validate / judge / package / submit / status
    / overseer). Returns a dispatcher key or None."""
    p = prompt.lower()
    if "validate" in p or "missing" in p:
        return "validate"
    if "package" in p:
        return "package"
    if "submit" in p:
        return "submit"
    if "overseer" in p or "review" in p:
        return "overseer"
    if "status" in p:
        return "status"
    # "judge" / "cassi" → judge_cassi, but NOT when paired with a drafting
    # verb (e.g. "draft a CASSI principle" must NOT route to judge_cassi).
    DRAFT_VERBS = ("draft", "create", "make", "write", "compose", "generate", "build",
                   "revise", "edit", "improve", "fix", "rewrite", "update")
    has_draft_verb = any(v in p for v in DRAFT_VERBS)
    if not has_draft_verb:
        if "judge" in p or (("cassi" in p) and "principle" not in p and "spec" not in p
                            and "benchmark" not in p and "solution" not in p):
            return "judge_cassi"
    return None


def _route_drafting(prompt: str) -> Optional[str]:
    """Match prompts that ask for a contribution-template (no LLM). Returns
    a dispatcher key or None. Only consulted when --agent=none."""
    p = prompt.lower()
    if any(v in p for v in ("contribute principle", "create principle", "draft principle")):
        return "principle"
    if any(v in p for v in ("contribute spec", "create spec", "draft spec")):
        return "spec"
    if any(v in p for v in ("contribute benchmark", "create benchmark", "draft benchmark")):
        return "benchmark"
    if any(v in p for v in ("contribute solution", "create solution", "draft solution")):
        return "solution"
    DRAFT_VERBS = ("draft", "create", "make", "write", "compose", "generate", "build",
                   "revise", "edit", "improve", "fix", "rewrite", "update")
    if any(v in p for v in DRAFT_VERBS):
        if "principle" in p:
            return "principle"
        if "spec" in p:
            return "spec"
        if "benchmark" in p:
            return "benchmark"
        if "solution" in p:
            return "solution"
    if "principle" in p:
        return "principle"
    if "spec" in p:
        return "spec"
    if "benchmark" in p:
        return "benchmark"
    if "solution" in p:
        return "solution"
    return None


def _rule_route(prompt: str) -> Optional[str]:
    """Back-compat helper exposed for tests: applies utility AND drafting rules.

    NOT used directly by the prompt dispatcher anymore; the dispatcher
    splits the two paths explicitly based on --agent.
    """
    return _route_utility(prompt) or _route_drafting(prompt)


def _dispatch_rule(name: str) -> int:
    """Run a matched deterministic subcommand."""
    here = Path(".")
    if name == "principle":
        console.print("→ intent: [cyan]contribute principle[/cyan]")
        contribute_cmd.principle()
    elif name == "spec":
        console.print("→ intent: [cyan]contribute spec[/cyan]")
        contribute_cmd.spec()
    elif name == "benchmark":
        console.print("→ intent: [cyan]contribute benchmark[/cyan]")
        contribute_cmd.benchmark()
    elif name == "solution":
        console.print("→ intent: [cyan]contribute solution[/cyan]")
        contribute_cmd.solution()
    elif name == "package":
        console.print("→ intent: [cyan]package[/cyan]")
        package_cmd.package(workspace=here, output_dir=here, skip_validate=False)
    elif name == "submit":
        console.print("→ intent: [cyan]submit --dry-run[/cyan]")
        submit_cmd.submit(workspace=here, dry_run=True)
    elif name == "validate":
        console.print("→ intent: [cyan]validate[/cyan]")
        validate_cmd.validate(workspace=here)
    elif name == "overseer":
        console.print("→ intent: [cyan]overseer review[/cyan]")
        overseer_cmd.review(submission=".")
    elif name == "judge_cassi":
        console.print("→ intent: [cyan]judge cassi[/cyan]")
        judge_cmd.cassi(submission=".")
    elif name == "status":
        console.print("→ intent: [cyan]status[/cyan]")
        status_cmd.status(workspace=here)
    else:
        return 2
    return 0


def _route_prompt(prompt: str, agent_name: str,
                  read_only: bool = False, auto_yes: bool = False) -> int:
    """Two-tier routing:
       1. Utility commands (validate/judge/package/submit/status/overseer) always
          dispatch deterministically — an LLM adds nothing.
       2. Everything else: if --agent=none, try the template-based contribute
          rules; otherwise hand off to the selected agent.

    When --agent claude is selected, tool use (Edit/Write/Bash) is ON by
    default; every change triggers a confirmation prompt. Pass --read-only
    to disable tool use entirely (text-only response).
    """
    console.print(f"[purple]✨ AI4Science[/purple]: [italic]{prompt!r}[/italic]")

    # Tier 1: utility commands — always deterministic.
    util = _route_utility(prompt)
    if util is not None:
        return _dispatch_rule(util)

    # Tier 2: drafting / open-ended.
    if agent_name == "none":
        # No agent selected: try the template-based contribute rules.
        draft = _route_drafting(prompt)
        if draft is not None:
            return _dispatch_rule(draft)
        console.print(
            "[yellow]No rule matched and --agent is 'none'.[/yellow]\n"
            "Pick an agent (`--agent claude` or `--agent codex`) or use one of:\n"
            "  ai4science contribute principle | spec | benchmark | solution\n"
            "  ai4science validate / judge cassi / overseer review / package / submit"
        )
        return 2

    agent = get_agent(agent_name, read_only=read_only, auto_yes=auto_yes)
    if not agent.is_available():
        reason = getattr(agent, "unavailable_reason", lambda: "")()
        console.print(f"[red]Agent {agent_name!r} not available:[/red] {reason}")
        return 2

    # Gather workspace context: any artifact .md files in cwd.
    workspace = Path(".").resolve()
    context_files = [p for p in (
        workspace / "principle.md",
        workspace / "spec.md",
        workspace / "benchmark.md",
        workspace / "solution.md",
    ) if p.exists()]

    # Any @-mentions in the prompt also become attached files (dedup'd).
    from ai4science.agents.mentions import parse_mentions
    mentioned = parse_mentions(prompt, workspace)
    extra = [p for p in mentioned if p not in context_files]
    context_files.extend(extra)
    if extra:
        rels = [str(p.relative_to(workspace)) for p in extra]
        console.print(f"[dim]📎 @attached: {', '.join(rels)}[/dim]")

    mode_label = "read-only" if read_only else "tool-use enabled"
    console.print(f"[dim]→ delegating to {agent_name!r} agent "
                  f"(workspace={workspace.name}, context files={len(context_files)}, "
                  f"mode={mode_label})[/dim]")
    if not read_only and agent_name == "claude":
        console.print(
            "[dim]   Edit/Write/Bash will prompt for confirmation. Use "
            "[cyan]--read-only[/cyan] to disable tool use, or [cyan]--yes[/cyan] to "
            "auto-approve all edits.[/dim]"
        )

    # When tool use is on, the agent prints progress to stderr (permission
    # prompts). Don't wrap in a status spinner; it would clobber the prompt.
    if read_only:
        with console.status(f"[purple]{agent_name} thinking…", spinner="dots"):
            result = agent.run_task(prompt, workspace, context_files)
    else:
        result = agent.run_task(prompt, workspace, context_files)

    if result.status == "ok":
        console.print()
        console.print(f"[bold]── {agent_name} response ──[/bold]")
        console.print(result.message)
        if getattr(result, "changed_files", None):
            console.print("\n[bold]Files the agent edited:[/bold]")
            for f in result.changed_files:
                console.print(f"  - {f}")
        if result.suggestions:
            console.print("\n[bold]Suggestions[/bold]")
            for s in result.suggestions:
                console.print(f"  - {s}")
        return 0
    elif result.status == "not_available":
        console.print(f"[yellow]{agent_name}: not available.[/yellow] {result.message}")
        return 2
    else:
        console.print(f"[red]{agent_name} error:[/red] {result.message}")
        return 1


def _pop_agent_flag(argv: List[str]) -> tuple[List[str], str, bool, bool]:
    """Strip --agent/-a, --read-only, --yes from argv.

    Returns (cleaned_argv, agent_name, read_only, auto_yes).

    Env defaults:
      AI4SCIENCE_AGENT       — agent name (default 'none')
      AI4SCIENCE_READ_ONLY   — '1' to default to read-only mode
      AI4SCIENCE_AUTO_YES    — '1' to default to auto-approve edits
    """
    agent = os.environ.get("AI4SCIENCE_AGENT", "none").lower()
    read_only = os.environ.get("AI4SCIENCE_READ_ONLY") == "1"
    auto_yes = os.environ.get("AI4SCIENCE_AUTO_YES") == "1"

    cleaned: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--agent", "-a") and i + 1 < len(argv):
            agent = argv[i + 1].lower()
            i += 2
            continue
        if a.startswith("--agent="):
            agent = a.split("=", 1)[1].lower()
            i += 1
            continue
        if a in ("--read-only", "--readonly"):
            read_only = True
            i += 1
            continue
        if a in ("--yes", "-y"):
            auto_yes = True
            i += 1
            continue
        cleaned.append(a)
        i += 1
    if agent not in ("none", "claude", "codex"):
        console.print(f"[yellow]Unknown --agent value {agent!r}; falling back to 'none'.[/yellow]")
        agent = "none"
    return cleaned, agent, read_only, auto_yes


def main() -> None:
    """Entry point that supports both `ai4science <subcommand>` and `ai4science "prompt"`."""
    argv, agent_name, read_only, auto_yes = _pop_agent_flag(sys.argv[1:])

    if argv and not argv[0].startswith("-"):
        registered = {
            "init", "contribute", "validate", "judge", "overseer",
            "package", "submit", "status", "version", "agents", "chat",
        }
        if argv[0] not in registered:
            # Prompt-first mode. Treat the whole argv as the user's prompt.
            prompt = " ".join(argv)
            sys.exit(_route_prompt(prompt, agent_name,
                                    read_only=read_only, auto_yes=auto_yes))

    # Subcommand mode: hand off to Typer with the cleaned argv.
    sys.argv = [sys.argv[0]] + argv
    app()


if __name__ == "__main__":
    main()
