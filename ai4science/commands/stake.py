"""ai4science stake — provider stake / collateral (the no-burn hold-reason).

Providers lock PWM to be eligible to serve/earn; stake is slashed for
unverified/bad results. Founders bootstrap without staking. Off-chain
accounting — the CLI moves no real tokens.

  add     --provider <id> --amount <pwm>     lock collateral
  remove  --provider <id> --amount <pwm>     unlock (if not slashed below it)
  slash   --provider <id> --amount <pwm> --reason ...   penalize a bad result
  status  [--provider <id>]                  staked + eligibility
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ai4science import staking

app = typer.Typer(help="Provider stake / collateral (lock PWM to be eligible).")
console = Console()


@app.command("add")
def add(
    provider_id: str = typer.Option(..., "--provider", "-p", help="Provider id."),
    amount: float = typer.Option(..., "--amount", "-a", help="PWM to stake."),
) -> None:
    """Lock PWM as collateral for a provider."""
    try:
        bal = staking.stake(provider_id, amount)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    elig = staking.is_eligible(provider_id)
    console.print(f"[green]✓[/green] Staked {amount:g} PWM to [cyan]{provider_id}[/cyan] "
                  f"→ total [bold]{bal:g} PWM[/bold] "
                  f"({'[green]eligible[/green]' if elig else f'[yellow]below {staking.MIN_STAKE_PWM:g} min[/yellow]'})")


@app.command("remove")
def remove(
    provider_id: str = typer.Option(..., "--provider", "-p"),
    amount: float = typer.Option(..., "--amount", "-a", help="PWM to unstake."),
) -> None:
    """Unlock staked PWM (cannot exceed the current balance)."""
    try:
        bal = staking.unstake(provider_id, amount)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[green]✓[/green] Unstaked {amount:g} PWM from [cyan]{provider_id}[/cyan] "
                  f"→ remaining [bold]{bal:g} PWM[/bold]")


@app.command("slash")
def slash(
    provider_id: str = typer.Option(..., "--provider", "-p"),
    amount: float = typer.Option(..., "--amount", "-a", help="PWM to slash."),
    reason: str = typer.Option(..., "--reason", help="Why (e.g. judge: silent_failure)."),
) -> None:
    """Penalize a provider's stake for a verified-bad result."""
    try:
        bal = staking.slash(provider_id, amount, reason)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[red]⚠ Slashed[/red] {amount:g} PWM from [cyan]{provider_id}[/cyan] "
                  f"({reason}) → remaining [bold]{bal:g} PWM[/bold]")
    if not staking.is_eligible(provider_id):
        console.print(f"[yellow]{provider_id} is now below the {staking.MIN_STAKE_PWM:g} "
                      "PWM minimum — ineligible until re-staked.[/yellow]")


@app.command("status")
def status(
    provider_id: Optional[str] = typer.Option(None, "--provider", "-p",
                                               help="One provider, or omit for all."),
) -> None:
    """Show staked PWM + eligibility."""
    if provider_id:
        rows = {provider_id: {"staked": staking.staked(provider_id),
                              "slashed": staking.slashed_total(provider_id),
                              "tier": staking.provider_tier(provider_id),
                              "eligible": staking.is_eligible(provider_id)}}
    else:
        rows = staking.summary()
    if not rows:
        console.print(f"[dim]No stake events yet.[/dim] Ledger: {staking.default_path()}")
        console.print(f"Minimum stake to be eligible (non-founder): "
                      f"[bold]{staking.MIN_STAKE_PWM:g} PWM[/bold]")
        return
    table = Table(title=f"Provider stake (min {staking.MIN_STAKE_PWM:g} PWM; "
                        "founders exempt)", show_lines=False)
    table.add_column("provider", style="cyan")
    table.add_column("tier")
    table.add_column("staked PWM", justify="right", style="bold")
    table.add_column("slashed", justify="right")
    table.add_column("eligible")
    for pid, s in sorted(rows.items()):
        elig = ("[green]yes[/green]" if s["eligible"]
                else "[yellow]no[/yellow]")
        note = " [dim](founder)[/dim]" if s["tier"] == "founder" else ""
        table.add_row(pid, s["tier"], f"{s['staked']:g}", f"{s['slashed']:g}",
                      elig + note)
    console.print(table)
