"""ai4science compute — wallet-bound GPU compute providers (Phase 0).

Subcommands:
  providers              list registered providers
  providers-add          register/replace a provider (founder tier)
  dispatch               write a job request to a provider's inbox
  status <job_id>        show the file-inbox handshake state
  verify <job_id>        run the judge on the result + record attribution
  credits                show verified-job credits per wallet

Trust model (see docs/COMPUTE_PROVIDERS_DESIGN.md): the deterministic
Physics Judge re-verifies every result, so providers are verified, not
trusted. The CLI never moves tokens.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ai4science.compute import (
    ComputeProvider, add_provider, load_registry, is_valid_eth_address,
)
from ai4science.compute.registry import get_provider, default_registry_path
from ai4science.compute.dispatch import dispatch_job, job_state, read_result
from ai4science.compute.attribution import verify_and_attribute, credit_summary

app = typer.Typer(help="Wallet-bound GPU compute providers (Phase 0).")
console = Console()


@app.command("providers")
def providers_list() -> None:
    """List registered compute providers."""
    provs = load_registry()
    if not provs:
        console.print(f"[dim]No providers registered.[/dim] Registry: "
                      f"{default_registry_path()}")
        console.print("Add one with: [cyan]ai4science compute providers-add "
                      "--id <id> --wallet 0x… --endpoint <dir>[/cyan]")
        return
    table = Table(title="Compute providers", show_lines=True)
    table.add_column("provider_id", style="cyan")
    table.add_column("wallet", style="magenta")
    table.add_column("tier")
    table.add_column("status")
    table.add_column("endpoint", style="dim")
    for p in provs:
        table.add_row(p.provider_id, p.wallet_address, p.trust_tier,
                      p.status, f"{p.endpoint_kind}:{p.endpoint_path}")
    console.print(table)


@app.command("providers-add")
def providers_add(
    provider_id: str = typer.Option(..., "--id", help="Provider identifier."),
    wallet: str = typer.Option(..., "--wallet", help="0x Ethereum address rewards accrue to."),
    endpoint: str = typer.Option(..., "--endpoint", help="Shared dir the provider polls for jobs."),
    label: str = typer.Option("", "--label", help="Human label."),
    tier: str = typer.Option("founder", "--tier", help="founder | approved | open."),
) -> None:
    """Register (or replace) a compute provider bound to a wallet."""
    if not is_valid_eth_address(wallet):
        console.print(f"[red]Invalid wallet address:[/red] {wallet!r} "
                      "(expected 0x + 40 hex chars)")
        raise typer.Exit(2)
    provider = ComputeProvider(
        provider_id=provider_id,
        wallet_address=wallet,
        endpoint_kind="file-inbox",
        endpoint_path=str(Path(endpoint).expanduser()),
        label=label,
        trust_tier=tier,
        status="active",
    )
    add_provider(provider)
    console.print(f"[green]✓[/green] Bound provider [cyan]{provider_id}[/cyan] "
                  f"→ wallet [magenta]{wallet}[/magenta] (tier={tier})")
    console.print(f"[dim]Registry: {default_registry_path()}[/dim]")


@app.command("dispatch")
def dispatch(
    provider_id: str = typer.Option(..., "--provider", "-p", help="Provider to dispatch to."),
    benchmark: str = typer.Option("", "--benchmark", "-b", help="Benchmark id (e.g. L3-003-001-001-T1)."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w"),
    solver_code: str = typer.Option("code/", "--solver", help="Solver code path."),
    run_command: str = typer.Option("python code/run_solver.py", "--run-command"),
    dataset_ref: str = typer.Option("", "--dataset", help="Dataset reference (gs:// or local)."),
) -> None:
    """Write a job request into the provider's inbox."""
    provider = get_provider(provider_id)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}. "
                      "List with [cyan]ai4science compute providers[/cyan].")
        raise typer.Exit(2)
    job = dispatch_job(
        provider=provider, workspace=workspace.resolve(),
        benchmark_id=benchmark, solver_code_path=solver_code,
        run_command=run_command, dataset_ref=dataset_ref,
    )
    console.print(f"[green]✓[/green] Dispatched job [cyan]{job.job_id}[/cyan] "
                  f"to [magenta]{provider_id}[/magenta]")
    console.print(f"  inbox:   {provider.endpoint_path}/job_{job.job_id}.request.json")
    console.print(f"  wallet:  {provider.wallet_address}")
    console.print(f"\n[dim]Poll with:[/dim] ai4science compute status {job.job_id} "
                  f"--provider {provider_id}")


@app.command("status")
def status(
    job_id: str = typer.Argument(..., help="Job id from dispatch."),
    provider_id: str = typer.Option(..., "--provider", "-p"),
) -> None:
    """Show the file-inbox handshake state for a job."""
    provider = get_provider(provider_id)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}")
        raise typer.Exit(2)
    st = job_state(Path(provider.endpoint_path), job_id)
    color = {"requested": "yellow", "acked": "cyan",
             "completed": "green", "missing": "red"}.get(st["state"], "white")
    console.print(f"Job [cyan]{job_id}[/cyan] — state: [{color}]{st['state']}[/{color}]")
    if "result" in st:
        r = st["result"]
        console.print(f"  certificate_hash: {r.get('certificate_hash', '—')}")
        console.print(f"  claimed metrics:  {r.get('metrics', '—')}")


@app.command("verify")
def verify(
    job_id: str = typer.Argument(..., help="Job id to verify."),
    provider_id: str = typer.Option(..., "--provider", "-p"),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w"),
    benchmark: str = typer.Option(None, "--benchmark", "-b",
                                   help="Benchmark tier file to judge (default benchmark.md)."),
) -> None:
    """Re-verify a returned result with the Physics Judge + record attribution."""
    provider = get_provider(provider_id)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}")
        raise typer.Exit(2)
    st = job_state(Path(provider.endpoint_path), job_id)
    result_manifest = st.get("result")
    job_meta = st.get("request") or {
        "job_id": job_id, "provider_id": provider_id,
        "wallet_address": provider.wallet_address, "benchmark_id": benchmark or "",
    }

    attribution = verify_and_attribute(
        workspace=workspace.resolve(), job=job_meta,
        result_manifest=result_manifest, benchmark=benchmark,
    )

    decision = attribution["judge_decision"]
    color = {"pass": "green", "fail": "red",
             "needs_review": "yellow"}.get(decision, "white")
    console.print(f"Judge decision: [{color}]{decision}[/{color}]")
    console.print(f"Silent failure: {attribution['silent_failure']}")
    console.print(f"Credit to [magenta]{attribution['wallet_address']}[/magenta]: "
                  f"[bold]{attribution['credit']}[/bold] verified-job credit(s)")
    console.print(f"[dim]Logged to reports/compute_attributions.jsonl[/dim]")
    if decision != "pass":
        console.print("[yellow]No credit awarded — judge did not return pass.[/yellow]")


@app.command("credits")
def credits(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w"),
) -> None:
    """Show verified-job credits per wallet (off-chain log)."""
    totals = credit_summary(workspace.resolve())
    if not totals:
        console.print("[dim]No attributions yet.[/dim]")
        return
    table = Table(title="Verified-job credits (off-chain)", show_lines=False)
    table.add_column("wallet", style="magenta")
    table.add_column("credits", justify="right")
    for wallet, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        table.add_row(wallet, str(n))
    console.print(table)
    console.print("[dim]Unit-less credits. PWM conversion + on-chain settlement "
                  "are platform-owned governance decisions.[/dim]")
