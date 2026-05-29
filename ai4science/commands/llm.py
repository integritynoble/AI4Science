"""ai4science llm — wallet-bound LLM providers (Phase 1).

Binds a wallet address to an LLM backend (anthropic / openai / gemini / …) and
an auth method (subscription / api_key / comparegpt). This is the supply side
of the token economy: when AI4Science uses a provider's LLM, usage accrues to
that provider's wallet (token accounting + PWM settlement are later phases).

  providers              list registered LLM providers
  providers-add          register/replace a provider (founder tier)
  check <id>             verify the provider's backend is reachable here
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ai4science.llm import (
    LLMProvider, BACKENDS, AUTH_METHODS, add_provider, load_registry,
    get_provider, default_registry_path,
)
from ai4science.compute.registry import is_valid_eth_address

app = typer.Typer(help="Wallet-bound LLM providers (subscription / api-key / comparegpt).")
console = Console()


@app.command("providers")
def providers_list() -> None:
    """List registered LLM providers."""
    provs = load_registry()
    if not provs:
        console.print(f"[dim]No LLM providers registered.[/dim] Registry: "
                      f"{default_registry_path()}")
        console.print("Add one with: [cyan]ai4science llm providers-add --id <id> "
                      "--wallet 0x… --backend anthropic --auth subscription[/cyan]")
        return
    table = Table(title="LLM providers", show_lines=True)
    table.add_column("provider_id", style="cyan")
    table.add_column("backend")
    table.add_column("auth")
    table.add_column("wallet", style="magenta")
    table.add_column("price×", justify="right")
    table.add_column("models", style="dim")
    table.add_column("status")
    for p in provs:
        table.add_row(p.provider_id, p.backend, p.auth, p.wallet_address,
                      f"{p.price_multiplier:g}", ",".join(p.models), p.status)
    console.print(table)


@app.command("providers-add")
def providers_add(
    provider_id: str = typer.Option(..., "--id", help="Provider identifier."),
    wallet: str = typer.Option(..., "--wallet", help="0x address usage revenue accrues to."),
    backend: str = typer.Option(..., "--backend", help=f"One of {', '.join(BACKENDS)}."),
    auth: str = typer.Option("subscription", "--auth", help=f"One of {', '.join(AUTH_METHODS)}."),
    models: str = typer.Option("*", "--models", help="Comma-separated model ids, or * for any."),
    price_multiplier: float = typer.Option(
        1.0, "--price-multiplier",
        help="Fraction of official per-token price (0.5 = half, for subscriptions)."),
    label: str = typer.Option("", "--label"),
    tier: str = typer.Option("founder", "--tier"),
) -> None:
    """Register (or replace) an LLM provider bound to a wallet."""
    if not is_valid_eth_address(wallet):
        console.print(f"[red]Invalid wallet address:[/red] {wallet!r}")
        raise typer.Exit(2)
    try:
        provider = LLMProvider(
            provider_id=provider_id, wallet_address=wallet, backend=backend.lower(),
            auth=auth.lower(), models=[m.strip() for m in models.split(",") if m.strip()],
            price_multiplier=price_multiplier, label=label, trust_tier=tier, status="active",
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    add_provider(provider)
    console.print(f"[green]✓[/green] Bound LLM provider [cyan]{provider_id}[/cyan]: "
                  f"[bold]{backend}[/bold] via {auth} → wallet [magenta]{wallet}[/magenta] "
                  f"(price× {price_multiplier:g})")
    console.print(f"[dim]Registry: {default_registry_path()}[/dim]")


@app.command("check")
def check(
    provider_id: str = typer.Argument(..., help="Provider id to verify."),
) -> None:
    """Verify a provider's backend is reachable from this server."""
    p = get_provider(provider_id)
    if p is None:
        console.print(f"[red]No such LLM provider:[/red] {provider_id}")
        raise typer.Exit(2)
    console.print(f"Provider [cyan]{p.provider_id}[/cyan]: {p.backend} via {p.auth} "
                  f"→ [magenta]{p.wallet_address}[/magenta]")

    if p.backend == "anthropic" and p.auth == "subscription":
        from ai4science.agents import ClaudeAgent
        agent = ClaudeAgent()
        if agent.is_available():
            console.print("[green]✓ reachable[/green] — the `claude` CLI is logged in "
                          "(subscription); Anthropic models incl. Opus 4.7 are served here.")
        else:
            console.print(f"[yellow]✗ not reachable:[/yellow] {agent.unavailable_reason()}")
            console.print("Fix: [cyan]npm install -g @anthropic-ai/claude-code[/cyan] "
                          "then [cyan]claude login[/cyan].")
            raise typer.Exit(1)
    elif p.backend == "openai" and p.auth == "subscription":
        from ai4science.agents import get_agent
        agent = get_agent("codex")
        if agent.is_available():
            console.print("[green]✓ reachable[/green] — the `codex` CLI is present with "
                          "ChatGPT subscription auth (~/.codex); GPT models are served here.")
        else:
            console.print(f"[yellow]✗ not reachable:[/yellow] {agent.unavailable_reason()}")
            console.print("Fix: [cyan]npm install -g @openai/codex[/cyan] then "
                          "[cyan]codex login[/cyan].")
            raise typer.Exit(1)
    else:
        console.print(f"[yellow]check for {p.backend}/{p.auth} not wired yet[/yellow] "
                      "(verifies anthropic + openai subscriptions; gemini/comparegpt next).")
