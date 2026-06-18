"""ai4science provider — become a paid compute provider in one command.

    ai4science login
    ai4science provider start --wallet 0xYourWallet --allow-exec

Registers this machine as an open compute provider bound to YOUR login + wallet
(no shared secret), then serves jobs over the relay. You earn PWM to your wallet
for each judge-verified job. The provider daemon authenticates as you, so anyone
can run it — not just the founders.
"""
from __future__ import annotations

import socket
from typing import Optional

import typer
from rich.console import Console

from ai4science import wallet as W

app = typer.Typer(help="Run your machine as a paid AI4Science compute provider.")
console = Console()

_REGISTER_PATH = "/api/v1/compute/providers"


@app.command("start")
def start(
    wallet_addr: str = typer.Option(..., "--wallet",
                                    help="Your 0x wallet — earns PWM for verified jobs."),
    provider_id: str = typer.Option("", "--id",
                                    help="Provider id (default: derived from hostname)."),
    kind: str = typer.Option("gpu", "--kind", help="What you provide: gpu | cpu."),
    price: float = typer.Option(0.3, "--price", help="PWM/hour you charge."),
    max_concurrent: int = typer.Option(1, "--max-concurrent",
                                       help="Jobs served at once (raise only if you truly run them in parallel)."),
    allow_exec: bool = typer.Option(False, "--allow-exec",
                                    help="REQUIRED to actually run dispatched code. Only on a host you trust."),
    once: bool = typer.Option(False, "--once", help="Process one job then exit (testing)."),
    base: Optional[str] = typer.Option(None, "--base", help="Relay base URL."),
) -> None:
    """Register this machine as a compute provider and start serving. One command:
    install ai4science, log in, run this with your wallet — you're earning."""
    token = W.platform_token()
    if not token:
        console.print("[red]Not logged in.[/red] Run [bold]ai4science login[/bold] first "
                      "(the provider daemon authenticates as you).")
        raise typer.Exit(2)
    if not wallet_addr.startswith("0x") or len(wallet_addr) < 6:
        console.print(f"[red]--wallet must be a 0x… address[/red] (got {wallet_addr!r})")
        raise typer.Exit(2)
    kind = kind.strip().lower()
    if kind not in ("gpu", "cpu"):
        console.print("[red]--kind must be gpu or cpu[/red]")
        raise typer.Exit(2)

    base_url = base or W.platform_base()
    pid = provider_id.strip() or (
        f"{socket.gethostname().lower().replace('.', '-')[:40] or 'host'}-{kind}")

    # 1. Register server-side (bound to this login + wallet).
    try:
        status, resp = W.http_post(base_url, _REGISTER_PATH, token, {
            "provider_id": pid, "wallet_address": wallet_addr, "kind": kind,
            "price_pwm_per_hour": price, "max_concurrent": max_concurrent})
    except Exception as e:
        console.print(f"[red]Registration request failed:[/red] {e}")
        raise typer.Exit(1)
    if status == 401:
        console.print("[red]Unauthorized.[/red] Your session may have expired — "
                      "run [bold]ai4science login[/bold] again.")
        raise typer.Exit(1)
    if status != 200 or not resp.get("success"):
        console.print(f"[red]Registration failed (HTTP {status}):[/red] "
                      f"{resp.get('detail', resp)}")
        raise typer.Exit(1)

    console.print(f"[green]✓ Registered provider[/green] [cyan]{pid}[/cyan] "
                  f"({kind}, {price:g} PWM/hr, serves {max_concurrent}) → "
                  f"[magenta]{wallet_addr}[/magenta]")
    if not allow_exec:
        console.print("[yellow]⚠ Without --allow-exec the daemon ACKs jobs but won't run "
                      "code.[/yellow] Re-run with [cyan]--allow-exec[/cyan] on a trusted "
                      "host to actually earn.")
    console.print(f"[bold]Serving[/bold] over {base_url} — Ctrl+C to stop.\n")

    from ai4science.compute.http_provider import serve_http
    provider = {"provider_id": pid, "wallet_address": wallet_addr, "kind": kind,
                "price_pwm_per_hour": price}

    def _ev(ev: str, data: dict) -> None:
        if ev in ("job_start", "job_done", "loop_error", "heartbeat_error"):
            console.print(f"[dim]· {ev}: {data}[/dim]")

    try:
        serve_http(provider, base_url, token=token, allow_exec=allow_exec,
                   once=once, on_event=_ev)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped serving (you stay registered; run start again to resume).[/dim]")
