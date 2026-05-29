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


@app.command("route")
def route(
    agent: str = typer.Argument(None, help="Agent to resolve (orchestration|checking|fast). "
                                           "Omit to show all."),
) -> None:
    """Show which LLM each agent routes to right now (with fallback)."""
    from ai4science.llm import routing

    agents = [agent] if agent else list(routing.AGENT_CHAINS)
    table = Table(title="Agent → LLM routing (live)", show_lines=True)
    table.add_column("agent", style="cyan")
    table.add_column("→ resolved")
    table.add_column("reason", justify="center")
    table.add_column("wallet", style="magenta")
    table.add_column("chain (✓ reachable / ✗ down)", style="dim")
    for ag in agents:
        chain = routing.AGENT_CHAINS.get(ag)
        if chain is None:
            console.print(f"[red]Unknown agent:[/red] {ag} "
                          f"(known: {', '.join(routing.AGENT_CHAINS)})")
            raise typer.Exit(2)
        r = routing.resolve(ag)
        reasoning = routing.AGENT_REASONING.get(ag, "medium")
        if r is None:
            resolved = "[red]none reachable[/red]"
            wallet = "—"
        else:
            tag = " [yellow](fallback)[/yellow]" if r.is_fallback else ""
            resolved = f"[green]{r.backend}:{r.model}[/green]{tag}"
            wallet = r.wallet or "—"
        # availability is cached-ish per backend within this call
        avail = {b: routing.backend_available(b) for b in {c[0] for c in chain}}
        chain_str = "  ".join(
            f"{'✓' if avail.get(b) else '✗'} {b}:{m}" for b, m in chain)
        table.add_row(ag, resolved, reasoning, wallet, chain_str)
    console.print(table)


@app.command("run")
def run(
    agent: str = typer.Argument(..., help="Agent: orchestration | checking | fast."),
    prompt: str = typer.Argument(..., help="The prompt to run."),
    timeout: int = typer.Option(300, "--timeout", help="Seconds."),
) -> None:
    """Run a prompt through an agent's routed LLM (with fallback + reasoning)."""
    from ai4science.llm import execute, routing
    if agent not in routing.AGENT_CHAINS:
        console.print(f"[red]Unknown agent:[/red] {agent} "
                      f"(known: {', '.join(routing.AGENT_CHAINS)})")
        raise typer.Exit(2)
    res = execute.run_agent(agent, prompt, timeout=timeout)
    if res.route is not None:
        r = res.route
        tag = " [yellow](fallback)[/yellow]" if r.is_fallback else ""
        console.print(f"[dim]{agent} → [green]{r.backend}:{r.model}[/green]{tag} "
                      f"· reasoning={r.reasoning} · wallet={r.wallet or '—'}[/dim]")
    if res.error:
        console.print(f"[red]error:[/red] {res.error}")
        raise typer.Exit(1)
    console.print(res.text)
    u, c = res.usage, res.cost
    if any(u.get(k) for k in ("input", "output", "total")):
        console.print(f"[dim]tokens: ↑{u.get('input') or '?'} ↓{u.get('output') or '?'} "
                      f"(total {u.get('total') or '?'})[/dim]")
    if c.get("pwm"):
        console.print(f"[dim]cost: ${c['usd_billed']:.4f} billed "
                      f"(${c['usd_official']:.4f} official) = "
                      f"[magenta]{c['pwm']:.4f} PWM[/magenta][/dim]")
    # Record to the consumption ledger (off-chain), attributed to the wallet.
    from ai4science.llm import ledger
    if res.route is not None:
        ledger.record(agent=agent, backend=res.route.backend, model=res.route.model,
                      wallet=res.route.wallet, usage=u, cost=c)


@app.command("prices")
def prices() -> None:
    """Show per-model prices and the PWM peg (point 9 + 14)."""
    from ai4science.llm import pricing
    console.print(f"[bold]1 PWM = ${pricing.PWM_USD:g}[/bold]  "
                  "[dim](AI4SCIENCE_PWM_USD)[/dim]\n")
    table = Table(title="Official list prices (USD per 1M tokens)", show_lines=False)
    table.add_column("model", style="cyan")
    table.add_column("input $/M", justify="right")
    table.add_column("output $/M", justify="right")
    table.add_column("output = PWM/M", justify="right", style="magenta")
    for model, (pin, pout) in pricing.PRICES_USD_PER_M.items():
        table.add_row(model, f"{pin:g}", f"{pout:g}",
                      f"{pricing.usd_to_pwm(pout):.3f}")
    console.print(table)
    console.print("[dim]Subscriptions bill at the provider's price× (0.5 = half). "
                  "Run a call's cost with [cyan]ai4science llm run[/cyan]; "
                  "totals with [cyan]ai4science llm spend[/cyan].[/dim]")


@app.command("spend")
def spend() -> None:
    """Show LLM spend per provider wallet (off-chain PWM ledger, point 6)."""
    from ai4science.llm import ledger
    s = ledger.summary()
    if not s["calls"]:
        console.print(f"[dim]No metered calls yet.[/dim] Ledger: {ledger.default_path()}")
        return
    table = Table(title="LLM spend per wallet (off-chain)", show_lines=False)
    table.add_column("wallet", style="magenta")
    table.add_column("calls", justify="right")
    table.add_column("USD billed", justify="right")
    table.add_column("PWM", justify="right", style="bold")
    for w, agg in sorted(s["per_wallet"].items(), key=lambda kv: -kv[1]["pwm"]):
        table.add_row(w, str(agg["calls"]), f"${agg['usd_billed']:.4f}",
                      f"{agg['pwm']:.4f}")
    console.print(table)
    console.print(f"[bold]Total:[/bold] {s['calls']} calls · "
                  f"${s['total_usd_billed']:.4f} = "
                  f"[magenta]{s['total_pwm']:.4f} PWM[/magenta]")


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
    elif p.backend == "gemini" and p.auth == "comparegpt":
        from ai4science.llm import gemini as gem
        if not gem.is_available():
            console.print("[yellow]✗ no Gemini key[/yellow] — set "
                          "AI4SCIENCE_GEMINI_API_KEY or ensure the comparegpt .env "
                          "has GEMINI_API_KEY.")
            raise typer.Exit(1)
        try:
            text, usage = gem.chat(
                [{"role": "user", "content": "Reply with exactly: GEMINI-OK"}])
            console.print(f"[green]✓ reachable[/green] — Gemini via the comparegpt key "
                          f"({gem.DEFAULT_MODEL}) replied {text.strip()[:32]!r} "
                          f"[dim](usage {usage})[/dim]")
        except Exception as e:
            console.print(f"[yellow]✗ call failed:[/yellow] {type(e).__name__}: {e}")
            raise typer.Exit(1)
    else:
        console.print(f"[yellow]check for {p.backend}/{p.auth} not wired yet.[/yellow]")
