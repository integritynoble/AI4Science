"""ai4science compute — wallet-bound GPU compute providers (Phase 0).

Subcommands:
  join                   become a CPU/GPU compute provider and earn PWM (open tier)
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
from ai4science.compute.attribution import verify_and_attribute, credit_summary

app = typer.Typer(help="Wallet-bound GPU compute providers (Phase 0).")
console = Console()


def _fmt_age(age_s) -> str:
    if age_s is None:
        return "never"
    age_s = int(age_s)
    if age_s < 90:
        return f"{age_s}s ago"
    if age_s < 5400:
        return f"{age_s // 60}m ago"
    if age_s < 172800:
        return f"{age_s // 3600}h ago"
    return f"{age_s // 86400}d ago"


def _liveness_label(state_age) -> str:
    state, _age = state_age
    # Compact for the table (age detail is shown on `dispatch`).
    return "[green]● online[/green]" if state == "online" else "[red]○ offline[/red]"


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
    from ai4science import staking
    from ai4science.compute.provider import liveness
    table = Table(title="Compute providers", show_lines=True)
    table.add_column("provider_id", style="cyan", no_wrap=True)
    table.add_column("kind")
    table.add_column("status")
    table.add_column("PWM/hr", justify="right")
    table.add_column("wallet", style="magenta", no_wrap=True)
    table.add_column("tier")
    table.add_column("eligible")
    for p in provs:
        elig = "[green]yes[/green]" if staking.is_eligible(p.provider_id) else "[yellow]no[/yellow]"
        disabled = "" if p.status == "active" else " [red](disabled)[/red]"
        w = p.wallet_address
        short = f"{w[:12]}…{w[-4:]}" if len(w) > 18 else w   # 0xf1Fa5803daA…7DEE
        table.add_row(p.provider_id, p.kind, _liveness_label(liveness(p.model_dump())),
                      f"{p.pwm_per_hour():g}",
                      short, p.trust_tier + disabled, elig)
    # Wide console so the 7-column table never wraps the wallet/provider id.
    from rich.console import Console as _Console
    _Console(width=120).print(table)


@app.command("providers-add")
def providers_add(
    provider_id: str = typer.Option(..., "--id", help="Provider identifier."),
    wallet: str = typer.Option(..., "--wallet", help="0x Ethereum address rewards accrue to."),
    endpoint: str = typer.Option(..., "--endpoint", help="Shared dir the provider polls for jobs."),
    label: str = typer.Option("", "--label", help="Human label."),
    tier: str = typer.Option("founder", "--tier", help="founder | approved | open."),
    kind: str = typer.Option("gpu", "--kind", help="gpu | cpu."),
    price_pwm_per_hour: float = typer.Option(
        0.0, "--price-pwm-per-hour", help="Provider-set compute price (PWM/hour)."),
    max_concurrent: int = typer.Option(
        1, "--max-concurrent",
        help="Max users served at once (counting semaphore). Default 1 — one "
             "job at a time per machine; raise it if your box can run more."),
) -> None:
    """Register (or replace) a compute provider bound to a wallet."""
    if not is_valid_eth_address(wallet):
        console.print(f"[red]Invalid wallet address:[/red] {wallet!r} "
                      "(expected 0x + 40 hex chars)")
        raise typer.Exit(2)
    try:
        provider = ComputeProvider(
            provider_id=provider_id,
            wallet_address=wallet,
            endpoint_kind="file-inbox",
            endpoint_path=str(Path(endpoint).expanduser()),
            label=label,
            kind=kind.lower(),
            price_pwm_per_hour=price_pwm_per_hour,
            max_concurrent=max_concurrent,
            trust_tier=tier,
            status="active",
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    add_provider(provider)
    console.print(f"[green]✓[/green] Bound [bold]{kind.lower()}[/bold] provider "
                  f"[cyan]{provider_id}[/cyan] → wallet [magenta]{wallet}[/magenta] "
                  f"(tier={tier}, {price_pwm_per_hour:g} PWM/hr)")
    console.print(f"[dim]Registry: {default_registry_path()}[/dim]")


@app.command("join")
def join(
    wallet: str = typer.Option(..., "--wallet",
                               help="Your 0x wallet — earns PWM when users run jobs on your box."),
    kind: str = typer.Option("gpu", "--kind", help="What you provide: gpu | cpu."),
    provider_id: str = typer.Option("", "--id", help="Provider id (default: derived)."),
    endpoint: str = typer.Option("", "--endpoint",
                                  help="Inbox dir you poll (default: ~/.config/ai4science/compute-inbox/<id>)."),
    price_pwm_per_hour: float = typer.Option(
        -1.0, "--price-pwm-per-hour",
        help="Your compute price (PWM/hour). Default: 0.30 gpu / 0.04 cpu."),
    max_concurrent: int = typer.Option(
        1, "--max-concurrent",
        help="How many users you serve at once. Default 1 (one job at a time); "
             "raise it only if your machine can truly run jobs in parallel."),
    label: str = typer.Option("", "--label", help="Human label."),
) -> None:
    """Become an open compute provider and earn PWM.

    Registers your machine as a community (open-tier) CPU/GPU provider bound to
    your wallet, then tells you how to start serving. When any user dispatches a
    job to you, they pay PWM to YOUR wallet (price × runtime); the Physics Judge
    re-verifies results, so you are paid for verified work, not trusted blindly.
    PWM is earned, never bought — this is one of the earning on-ramps.
    """
    kind = kind.lower()
    if kind not in ("gpu", "cpu"):
        console.print(f"[red]--kind must be gpu or cpu, got {kind!r}[/red]")
        raise typer.Exit(2)
    if not is_valid_eth_address(wallet):
        console.print(f"[red]Invalid wallet address:[/red] {wallet!r} "
                      "(expected 0x + 40 hex chars)")
        raise typer.Exit(2)
    if price_pwm_per_hour < 0:
        price_pwm_per_hour = 0.30 if kind == "gpu" else 0.04
    pid = provider_id or f"{kind}-{wallet[-6:].lower()}"
    ep = endpoint or str(default_registry_path().parent / "compute-inbox" / pid)
    try:
        provider = ComputeProvider(
            provider_id=pid,
            wallet_address=wallet,
            endpoint_kind="file-inbox",
            endpoint_path=str(Path(ep).expanduser()),
            label=label or f"Community {kind.upper()} provider",
            kind=kind,
            price_pwm_per_hour=price_pwm_per_hour,
            max_concurrent=max_concurrent,
            trust_tier="open",
            status="active",
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    Path(provider.endpoint_path).expanduser().mkdir(parents=True, exist_ok=True)
    add_provider(provider)

    console.print(f"[green]✓ You're registered as a compute provider![/green]")
    console.print(f"  id:       [cyan]{pid}[/cyan]  ({kind}, {price_pwm_per_hour:g} PWM/hr, "
                  f"serves {max_concurrent} at once)")
    console.print(f"  earns to: [magenta]{wallet}[/magenta]")
    console.print(f"  inbox:    {provider.endpoint_path}")
    console.print("\n[bold]How you earn PWM:[/bold] when a user runs a job on your box, "
                  "they pay PWM (price × runtime) to your wallet. Verified by the "
                  "Physics Judge, so you're paid for real work.")
    console.print("\n[bold]Start serving[/bold] (executes dispatched code — only on a host "
                  "you trust):")
    console.print(f"  [cyan]ai4science compute serve -p {pid} --allow-exec[/cyan]")
    console.print(f"[dim]Track earnings:[/dim] ai4science compute spend   "
                  f"[dim]· registry:[/dim] {default_registry_path()}")


@app.command("select")
def select(
    kind: Optional[str] = typer.Option(None, "--kind", help="gpu | cpu (omit for any)."),
) -> None:
    """Pick the best eligible compute provider of a kind (cheapest PWM/hr)."""
    from ai4science.compute.pricing import select as pick, eligible_providers
    p = pick(kind)
    if p is None:
        console.print(f"[yellow]No eligible {kind or 'compute'} provider available.[/yellow]")
        console.print("[dim](needs active + stake-eligible; stake with "
                      "[/dim][cyan]ai4science stake add[/cyan][dim]).[/dim]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Selected[/green] [cyan]{p.provider_id}[/cyan] "
                  f"({p.kind}, {p.pwm_per_hour():g} PWM/hr) → wallet "
                  f"[magenta]{p.wallet_address}[/magenta]")
    others = [x for x in eligible_providers(kind) if x.provider_id != p.provider_id]
    if others:
        console.print("[dim]also eligible: "
                      + ", ".join(f"{x.provider_id} ({x.pwm_per_hour():g} PWM/hr)"
                                  for x in others) + "[/dim]")


@app.command("spend")
def spend(
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Omit for the global ledger."),
) -> None:
    """Show priced compute earnings (PWM) per provider wallet."""
    from ai4science.compute.attribution import pwm_summary
    totals = pwm_summary(workspace.resolve() if workspace else None)
    totals = {w: v for w, v in totals.items() if v}
    if not totals:
        console.print("[dim]No priced compute jobs yet[/dim] "
                      "(providers earn PWM only on a verified pass, priced at "
                      "their PWM/hr rate).")
        return
    table = Table(title="Compute earnings per wallet (priced, off-chain)")
    table.add_column("wallet", style="magenta")
    table.add_column("PWM", justify="right", style="bold")
    for w, v in sorted(totals.items(), key=lambda kv: -kv[1]):
        table.add_row(w, f"{v:.4f}")
    console.print(table)
    console.print(f"[bold]Total:[/bold] {sum(totals.values()):.4f} PWM "
                  "[dim](unit credits via [/dim][cyan]ai4science compute credits[/cyan][dim])[/dim]")


def _http_or_exit():
    """An HttpTransport for the relay, or exit with a login hint."""
    from ai4science.compute.transport import select
    _m, tx = select(None)
    if not getattr(tx, "token", ""):
        console.print("[red]Not logged in.[/red] Run [cyan]ai4science login[/cyan] "
                      "to use a remote provider.")
        raise typer.Exit(2)
    return tx


@app.command("dispatch")
def dispatch(
    provider_id: str = typer.Option(..., "--provider", "-p", help="Provider to dispatch to."),
    benchmark: str = typer.Option("", "--benchmark", "-b", help="Benchmark id (e.g. L3-003-001-001-T1)."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w"),
    run_command: str = typer.Option("python code/run_solver.py", "--run-command"),
    dataset_ref: str = typer.Option("", "--dataset", help="Dataset reference (gs:// or local)."),
    max_runtime_s: int = typer.Option(3600, "--max-runtime-s", help="Runtime cap (PWM is bounded by this)."),
) -> None:
    """Dispatch a job to a provider over the HTTPS relay (needs `ai4science login`)."""
    tx = _http_or_exit()
    try:
        job = tx.dispatch(provider_id=provider_id, run_command=run_command,
                          workspace=workspace.resolve(), dataset_ref=dataset_ref,
                          max_runtime_s=max_runtime_s)
    except Exception as e:
        console.print(f"[red]dispatch failed:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Dispatched job [cyan]{job['job_id']}[/cyan] "
                  f"to [magenta]{provider_id}[/magenta] (state {job.get('state')})")
    console.print(f"\n[dim]Poll with:[/dim] ai4science compute status "
                  f"{job['job_id']} --provider {provider_id}")


@app.command("status")
def status(
    job_id: str = typer.Argument(..., help="Job id from dispatch."),
    provider_id: str = typer.Option("", "--provider", "-p"),
) -> None:
    """Show a job's state (via the relay)."""
    tx = _http_or_exit()
    try:
        job = tx.poll(job_id)
    except Exception as e:
        console.print(f"[red]status failed:[/red] {e}")
        raise typer.Exit(1)
    state = job.get("state", "unknown")
    color = {"requested": "yellow", "acked": "cyan",
             "completed": "green"}.get(state, "white")
    console.print(f"Job [cyan]{job_id}[/cyan] — state: [{color}]{state}[/{color}]")
    r = job.get("result") or {}
    if r:
        console.print(f"  certificate_hash: {r.get('certificate_hash', '—')}")
        console.print(f"  metrics:          {r.get('metrics', '—')}")


@app.command("verify")
def verify(
    job_id: str = typer.Argument(..., help="Job id to verify."),
    provider_id: str = typer.Option(..., "--provider", "-p"),
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace to judge. Default: a temp dir with the downloaded reconstruction."),
    benchmark: str = typer.Option(None, "--benchmark", "-b",
                                   help="Benchmark tier file to judge (default benchmark.md)."),
) -> None:
    """Re-verify a returned result with the Physics Judge + record attribution.

    Polls the relay, downloads the reconstruction, and runs the deterministic
    judge locally (no LLM in the verdict path)."""
    import tempfile
    tx = _http_or_exit()
    try:
        job = tx.poll(job_id)
    except Exception as e:
        console.print(f"[red]verify failed:[/red] {e}")
        raise typer.Exit(1)
    if job.get("state") != "completed":
        console.print(f"[yellow]Job {job_id} not complete (state {job.get('state')}).[/yellow]")
        raise typer.Exit(1)

    ws = workspace.resolve() if workspace else Path(tempfile.mkdtemp(prefix=f"a4s-verify-{job_id}-"))
    tx.download_reconstruction(job, ws)
    console.print(f"[dim]workspace: {ws} (downloaded reconstruction)[/dim]")
    job_meta = {"job_id": job_id, "provider_id": provider_id,
                "wallet_address": "", "benchmark_id": benchmark or ""}
    attribution = verify_and_attribute(
        workspace=ws, job=job_meta, result_manifest=job.get("result"),
        benchmark=benchmark)

    decision = attribution["judge_decision"]
    color = {"pass": "green", "fail": "red",
             "needs_review": "yellow"}.get(decision, "white")
    console.print(f"Judge decision: [{color}]{decision}[/{color}]")
    console.print(f"Silent failure: {attribution['silent_failure']}")
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
    base: Optional[str] = typer.Option(
        None, "--base", help="Relay base URL (default https://physicsworldmodel.org)."),
    provider_key: Optional[str] = typer.Option(
        None, "--provider-key", help="Provider auth key (COMPUTE_PROVIDER_KEY)."),
    modal: bool = typer.Option(
        False, "--modal",
        help="Run claimed jobs on Modal.com (serverless GPU) instead of locally. "
             "Use with -p modal-gpu; needs a `modal` login on this host."),
) -> None:
    """Run the provider-side poller on this GPU box, over the HTTP relay.

    Claims jobs from physicsworldmodel.org, runs the dispatched solver, and
    returns results — no pwm repo / git needed. This executes dispatched code,
    so only pass --allow-exec on a host where you trust the dispatcher.

    With --modal, this host is a *bridge*: it claims modal-gpu jobs from the
    relay and runs each on an on-demand Modal cloud GPU (the founder's Modal
    account pays Modal; the user pays PWM — earn-first)."""
    import os
    from ai4science.compute.http_provider import serve_http

    executor = None
    if modal:
        from ai4science.compute.modal_runner import run_solver_modal
        executor = run_solver_modal

    provider = get_provider(provider_id)
    if provider is None:                       # fall back to founder/Modal defaults
        from ai4science.compute.founders import all_providers
        provider = next((p for p in all_providers()
                         if p.provider_id == provider_id), None)
    if provider is None:
        console.print(f"[red]No such provider:[/red] {provider_id}. "
                      "Register it first with [cyan]ai4science compute providers-add[/cyan].")
        raise typer.Exit(2)

    if not allow_exec:
        console.print("[yellow]⚠ Running WITHOUT --allow-exec:[/yellow] jobs will be "
                      "claimed but their solver commands will NOT run. Re-run with "
                      "[cyan]--allow-exec[/cyan] on a trusted host to execute them.")

    relay_base = base or os.environ.get("PWM_BASE") or "https://physicsworldmodel.org"
    key = provider_key or os.environ.get("COMPUTE_PROVIDER_KEY", "")
    console.print(f"[bold purple]ai4science compute serve[/bold purple] (HTTP relay) — "
                  f"provider [cyan]{provider_id}[/cyan] via [green]{relay_base}[/green]")
    console.print(f"  exec: {'[green]enabled[/green]' if allow_exec else '[yellow]disabled[/yellow]'}"
                  f"   mode: {'once' if once else f'polling every {interval}s'}\n")

    def _ev(kind, payload):
        if kind == "job_start":
            console.print(f"[cyan]▶ job {payload['job_id']}[/cyan] claimed")
        elif kind == "job_done":
            tag = "[green]ran[/green]" if payload.get("solver_ran") else "[yellow]not run[/yellow]"
            console.print(f"  [green]✓ job {payload['job_id']}[/green] {tag}")
        elif kind in ("loop_error", "heartbeat_error"):
            console.print(f"  [yellow]⚠ {payload.get('error')}[/yellow]")

    if modal:
        console.print("  [magenta]backend: Modal.com[/magenta] (serverless GPU bridge)\n")

    try:
        serve_http(provider.model_dump(), relay_base, provider_key=key,
                   allow_exec=allow_exec, interval_s=interval, once=once,
                   executor=executor, on_event=_ev)
    except KeyboardInterrupt:
        console.print("\n[dim](stopped)[/dim]")
    if once:
        console.print("[dim]Done (--once).[/dim]")


@app.command("credits")
def credits(
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Sum a single workspace's local log. Default: the canonical "
             "aggregate ledger across all verified jobs."),
) -> None:
    """Show verified-job credits per wallet (off-chain log)."""
    totals = credit_summary(workspace.resolve() if workspace else None)
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
