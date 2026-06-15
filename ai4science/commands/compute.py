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
from ai4science.compute import gitsync
from ai4science.compute.registry import get_provider, default_registry_path
from ai4science.compute.dispatch import dispatch_job, job_state, read_result
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
    allow_detached_workspace: bool = typer.Option(
        False, "--allow-detached-workspace",
        help="Permit --git-sync with a workspace outside the synced repo. "
             "Same-machine only; cross-machine solves lose the reconstruction "
             "return path."),
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
            ws_abs = workspace.resolve()
            try:
                ws_abs.relative_to(repo.resolve())
            except ValueError:
                detail = (f"workspace {ws_abs} is outside the synced repo {repo}. "
                          "Cross-machine solves need it inside the repo so the "
                          "result + reconstruction return over git "
                          f"(e.g. {Path(provider.endpoint_path).expanduser()}/ws/<job>/).")
                if allow_detached_workspace:
                    console.print(f"[yellow]⚠ {detail}[/yellow]")
                    console.print("[yellow]  Proceeding (same-machine only).[/yellow]")
                else:
                    console.print(f"[red]✗ {detail}[/red]")
                    console.print("Pass [cyan]--allow-detached-workspace[/cyan] "
                                  "to override (same-machine only).")
                    raise typer.Exit(2)
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

    # Liveness: tell the user up-front if the provider isn't currently serving,
    # so a job that will sit in `requested` isn't mistaken for a working dispatch.
    from ai4science.compute.provider import liveness
    state, age = liveness(provider.model_dump())
    if state == "online":
        console.print(f"  provider: [green]● online[/green] "
                      f"[dim](heartbeat {_fmt_age(age)})[/dim] — should run shortly.")
    else:
        console.print(f"  provider: [red]○ offline[/red] "
                      f"[dim](last heartbeat {_fmt_age(age)})[/dim] — "
                      "job is [yellow]queued[/yellow]; it runs when the server's "
                      "serve loop is back up. Check with "
                      f"[cyan]ai4science compute status {job.job_id}[/cyan].")

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
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace to judge. Default: the job request's stored workspace."),
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
    request = st.get("request")
    job_meta = request or {
        "job_id": job_id, "provider_id": provider_id,
        "wallet_address": provider.wallet_address, "benchmark_id": benchmark or "",
    }

    # Default the workspace to the one recorded in the job request, so the judge
    # runs against the actual solve dir rather than the caller's cwd. Uses the
    # same repo-relative resolution as the poller, so a job dispatched from
    # another machine (foreign absolute path) still resolves against THIS
    # machine's checkout of the shared repo — no -w needed.
    if workspace is None:
        if request:
            from ai4science.compute.provider import _resolve_workspace
            workspace = _resolve_workspace(request, Path(provider.endpoint_path))
            how = ("from job request" if Path(request.get("workspace", "")).expanduser().is_dir()
                   else "via repo-relative" if request.get("workspace_repo_relative")
                   else "from job request")
        else:
            workspace = Path(".")
            how = "cwd fallback"
        console.print(f"[dim]workspace: {workspace} ({how})[/dim]")

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
