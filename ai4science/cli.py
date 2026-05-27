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
       ai4science status

2. **Prompt-first mode** (one-shot):
       ai4science "Help me create a CASSI spec and benchmark"
       ai4science "Validate my PWM contribution and tell me what is missing"

   v0.1 routes prompts via a rule-based intent detector (no LLM yet).
   Stage 2 will swap the router for a real agent backend (Claude Agent SDK
   for AI4Science role, OpenAI Codex for AI Overseer role).
"""
from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console

from ai4science import __version__
from ai4science.commands import (
    init as init_cmd,
    contribute as contribute_cmd,
    validate as validate_cmd,
    judge as judge_cmd,
    overseer as overseer_cmd,
    package as package_cmd,
    submit as submit_cmd,
    status as status_cmd,
)

console = Console()

# A custom Typer app that accepts a free-form prompt as the first positional
# argument when no subcommand matches. We achieve this by hooking the no-args
# callback and inspecting sys.argv.
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


@app.command("version", help="Print the AI4Science CLI version.")
def version_cmd() -> None:
    console.print(f"ai4science {__version__}")


# ─── Prompt-first dispatch ─────────────────────────────────────────────


def _route_prompt(prompt: str) -> int:
    """Rule-based intent dispatch for prompt-first mode (v0.1, no LLM).

    Calls each command function with explicit arguments — Typer's default
    OptionInfo objects only resolve when the function is invoked through
    the CLI dispatcher, not when called directly.
    """
    from pathlib import Path as _Path  # local import to keep top of module clean
    p = prompt.lower()
    here = _Path(".")
    console.print(f"[purple]✨ AI4Science[/purple] (v0.1 rule-based routing): [italic]{prompt!r}[/italic]")

    # Order matters: more-specific intents first.
    if "judge" in p or "cassi" in p:
        console.print("→ intent: [cyan]judge cassi[/cyan]")
        console.print("[dim]Run:[/dim] ai4science judge cassi --submission .")
        judge_cmd.cassi(submission=".")
        return 0

    if "package" in p:
        console.print("→ intent: [cyan]package[/cyan]")
        console.print("[dim]Run:[/dim] ai4science package")
        package_cmd.package(workspace=here, output_dir=here, skip_validate=False)
        return 0

    if "submit" in p:
        console.print("→ intent: [cyan]submit --dry-run[/cyan]")
        console.print("[dim]Run:[/dim] ai4science submit --dry-run")
        submit_cmd.submit(workspace=here, dry_run=True)
        return 0

    if "validate" in p or "missing" in p or "check" in p:
        console.print("→ intent: [cyan]validate[/cyan]")
        validate_cmd.validate(workspace=here)
        return 0

    if "overseer" in p or "review" in p:
        console.print("→ intent: [cyan]overseer review[/cyan]")
        overseer_cmd.review(submission=".")
        return 0

    # contribute intents — longer-match first
    if "principle" in p:
        console.print("→ intent: [cyan]contribute principle[/cyan]")
        contribute_cmd.principle()
        return 0
    if "spec" in p:
        console.print("→ intent: [cyan]contribute spec[/cyan]")
        contribute_cmd.spec()
        return 0
    if "benchmark" in p:
        console.print("→ intent: [cyan]contribute benchmark[/cyan]")
        contribute_cmd.benchmark()
        return 0
    if "solution" in p:
        console.print("→ intent: [cyan]contribute solution[/cyan]")
        contribute_cmd.solution()
        return 0

    if "init" in p or "new" in p or "start" in p:
        console.print("→ intent: [cyan]init[/cyan]")
        console.print("[yellow]Tell me the project name:[/yellow] ai4science init <name>")
        return 0

    if "status" in p:
        console.print("→ intent: [cyan]status[/cyan]")
        status_cmd.status(workspace=here)
        return 0

    console.print(
        "[yellow]Could not route this prompt with v0.1 rules.[/yellow]\n"
        "Try a subcommand instead — see [cyan]ai4science --help[/cyan].\n\n"
        "[dim]Stage 2 will route arbitrary English through a real agent backend "
        "(Claude Agent SDK or OpenAI Codex). For now, please use one of:[/dim]\n"
        "  ai4science contribute principle\n"
        "  ai4science contribute spec\n"
        "  ai4science contribute benchmark\n"
        "  ai4science contribute solution\n"
        "  ai4science validate\n"
        "  ai4science judge cassi --submission .\n"
        "  ai4science overseer review --submission .\n"
        "  ai4science package\n"
        "  ai4science submit --dry-run"
    )
    return 2  # exit code: command not understood


def main() -> None:
    """Entry point that supports BOTH `ai4science <subcommand>` and `ai4science "prompt"`."""
    # If the first arg looks like a free-form prompt (not a registered subcommand),
    # route it through _route_prompt instead of Typer's subcommand parser.
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("-"):
        registered = {
            "init", "contribute", "validate", "judge", "overseer",
            "package", "submit", "status", "version", "--help", "-h",
        }
        if argv[0] not in registered:
            # Prompt-first mode. Take the FULL argv as the prompt (handles unquoted prompts too).
            prompt = " ".join(argv)
            sys.exit(_route_prompt(prompt))

    # Otherwise fall through to Typer.
    app()


if __name__ == "__main__":
    main()
