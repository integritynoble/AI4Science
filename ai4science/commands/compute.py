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
from ai4science.compute import gitsync
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
    git_sync: bool = typer.Option(
        False, "--git-sync",
        help="Inbox is a git-shared dir: pull before writing, commit+push the "
             "request so a provider on another machine receives it."),
) -> None:
    """Write a job request into the provider's inbox."""
    provider = get_provider(provider_id)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}. "
                      "List with [cyan]ai4science compute providers[/cyan].")
        raise typer.Exit(2)

    repo = None
    if git_sync:
        repo = gitsync.find_repo_root(Path(provider.endpoint_path))
        if repo is None:
            console.print(f"[yellow]⚠ --git-sync:[/yellow] {provider.endpoint_path} "
                          "is not in a git repo; writing locally only.")
        else:
            ok, msg = gitsync.pull(repo)
            console.print(f"[dim]git pull: {'ok' if ok else 'FAILED — ' + msg}[/dim]")

    job = dispatch_job(
        provider=provider, workspace=workspace.resolve(),
        benchmark_id=benchmark, solver_code_path=solver_code,
        run_command=run_command, dataset_ref=dataset_ref,
    )
    console.print(f"[green]✓[/green] Dispatched job [cyan]{job.job_id}[/cyan] "
                  f"to [magenta]{provider_id}[/magenta]")
    console.print(f"  inbox:   {provider.endpoint_path}/job_{job.job_id}.request.json")
    console.print(f"  wallet:  {provider.wallet_address}")

    if repo is not None:
        req = Path(provider.endpoint_path).expanduser() / f"job_{job.job_id}.request.json"
        ok, msg = gitsync.commit_push(repo, [req],
                                      f"compute: dispatch job {job.job_id} → {provider_id}")
        if ok:
            console.print("[green]✓[/green] Pushed request to git "
                          "(provider will pull it on next poll).")
        else:
            console.print(f"[yellow]⚠ git push failed:[/yellow] {msg}")

    console.print(f"\n[dim]Poll with:[/dim] ai4science compute status {job.job_id} "
                  f"--provider {provider_id}" + (" --git-sync" if git_sync else ""))


@app.command("status")
def status(
    job_id: str = typer.Argument(..., help="Job id from dispatch."),
    provider_id: str = typer.Option(..., "--provider", "-p"),
    git_sync: bool = typer.Option(
        False, "--git-sync", help="git pull first to see a remote provider's progress."),
) -> None:
    """Show the file-inbox handshake state for a job."""
    provider = get_provider(provider_id)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}")
        raise typer.Exit(2)
    if git_sync:
        repo = gitsync.find_repo_root(Path(provider.endpoint_path))
        if repo is not None:
            ok, msg = gitsync.pull(repo)
            console.print(f"[dim]git pull: {'ok' if ok else 'FAILED — ' + msg}[/dim]")
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
    git_sync: bool = typer.Option(
        False, "--git-sync", help="git pull first to fetch the provider's result."),
) -> None:
    """Re-verify a returned result with the Physics Judge + record attribution."""
    provider = get_provider(provider_id)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}")
        raise typer.Exit(2)
    if git_sync:
        repo = gitsync.find_repo_root(Path(provider.endpoint_path))
        if repo is not None:
            ok, msg = gitsync.pull(repo)
            console.print(f"[dim]git pull: {'ok' if ok else 'FAILED — ' + msg}[/dim]")
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


@app.command("serve")
def serve(
    provider_id: str = typer.Option(..., "--provider", "-p",
                                     help="Which registered provider this host fulfills."),
    once: bool = typer.Option(False, "--once",
                               help="Process currently-pending jobs and exit (cron-friendly)."),
    interval: int = typer.Option(5, "--interval", help="Poll interval seconds."),
    allow_exec: bool = typer.Option(
        False, "--allow-exec",
        help="REQUIRED to actually run dispatched solver commands. Without it "
             "the poller acks jobs but refuses to execute code (safety gate)."),
    git_sync: bool = typer.Option(
        False, "--git-sync",
        help="Inbox is a git-shared dir: pull new requests each pass, push "
             "results back. Use this when the dispatcher is on another machine."),
) -> None:
    """Run the provider-side poller on this GPU box.

    Watches the provider's inbox for job requests, runs the dispatched
    solver, and writes results back. This executes dispatched code —
    only pass --allow-exec on a host where you trust the dispatcher
    (Phase 0: the founder dispatching to their own GPU)."""
    from ai4science.compute.provider import serve as serve_loop

    provider = get_provider(provider_id)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}. "
                      "Register it first with [cyan]ai4science compute providers-add[/cyan].")
        raise typer.Exit(2)

    if not allow_exec:
        console.print("[yellow]⚠ Running WITHOUT --allow-exec:[/yellow] jobs will be "
                      "acked but their solver commands will NOT run. Re-run with "
                      "[cyan]--allow-exec[/cyan] on a trusted host to execute them.")

    provider_dict = provider.model_dump()
    sync_label = "[green]git-synced[/green]" if git_sync else "local-only"
    console.print(f"[bold purple]ai4science compute serve[/bold purple] — "
                  f"provider [cyan]{provider_id}[/cyan]")
    console.print(f"  wallet:  [magenta]{provider.wallet_address}[/magenta]")
    console.print(f"  inbox:   {provider.endpoint_path}  ({sync_label})")
    console.print(f"  exec:    "
                  f"{'[green]enabled[/green]' if allow_exec else '[yellow]disabled[/yellow]'}")
    console.print(f"  mode:    "
                  f"{'once' if once else f'polling every {interval}s (Ctrl-C to stop)'}\n")

    def _log(kind: str, payload: dict):
        if kind == "start" and payload.get("git_sync") is False and git_sync:
            console.print("[yellow]⚠ --git-sync requested but inbox is not in a git "
                          "repo — running local-only.[/yellow]")
        elif kind == "sync_warn":
            console.print(f"[yellow]⚠ {payload['error']}[/yellow]")
        elif kind == "sync_pull" and not payload.get("ok"):
            console.print(f"[yellow]⚠ git pull failed: {payload.get('msg', '')}[/yellow]")
        elif kind == "sync_push":
            if payload.get("ok"):
                console.print(f"  [green]↥ pushed result for {payload['job_id']}[/green]")
            else:
                console.print(f"  [yellow]⚠ push failed for {payload['job_id']}: "
                              f"{payload.get('msg', '')}[/yellow]")
        elif kind == "job_start":
            console.print(f"[cyan]▶ job {payload['job_id']}[/cyan] picked up")
        elif kind == "job_done":
            ran = payload.get("solver_ran")
            tag = "[green]ran[/green]" if ran else "[yellow]not run[/yellow]"
            console.print(f"  [green]✓ job {payload['job_id']}[/green] {tag} → "
                          f"cert {str(payload.get('certificate_hash', '—'))[:14]}…")
        elif kind == "job_error":
            console.print(f"  [red]✗ job {payload['job_id']}: {payload['error']}[/red]")

    try:
        serve_loop(provider_dict, interval_s=interval, once=once,
                   allow_exec=allow_exec, git_sync=git_sync, on_event=_log)
    except KeyboardInterrupt:
        console.print("\n[dim](stopped)[/dim]")

    if once:
        console.print("[dim]Done (--once).[/dim]")


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
