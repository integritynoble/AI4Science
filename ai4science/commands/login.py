"""ai4science login / whoami / logout — onboarding (points 4–6).

`login` lets a user choose how the agent is powered: their OWN LLM
(subscription or API key — like `claude login` / `codex login`) or the local
hot-key PWM wallet (pay per use). Works interactively or via flags (scriptable).
"""
from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console

from ai4science import pwm_account
from ai4science import user as user_cfg
from ai4science import wallet as local_wallet

console = Console()


def _login_pwm(base: Optional[str]) -> None:
    """Device-flow login to a physicsworldmodel.org account (token only —
    the wallet private key is never requested or stored)."""
    target = (base or pwm_account.DEFAULT_BASE).rstrip("/")
    try:
        acct = pwm_account.login_device_flow(target, echo=console.print)
    except Exception as e:
        console.print(f"[red]login failed:[/red] {e}")
        raise typer.Exit(2)
    who = acct.get("email") or f"user #{acct.get('user_id')}"
    console.print(f"[green]✓ Logged in to {target}[/green] as [bold]{who}[/bold]"
                  + (f"  wallet [magenta]{acct['wallet']}[/magenta]" if acct.get("wallet") else ""))
    console.print("[dim]  stored: a revocable pwm_ API key (chmod 600) — never a private key.\n"
                  "  The PWM gate now uses it automatically when AI4SCIENCE_PWM_GATE=1.[/dim]")


def _reachable(provider: str, auth: str) -> Optional[bool]:
    """Best-effort reachability for subscription providers (None = unknown)."""
    try:
        if provider == "anthropic" and auth == "subscription":
            from ai4science.agents import ClaudeAgent
            return ClaudeAgent().is_available()
        if provider == "openai" and auth == "subscription":
            from ai4science.agents import get_agent
            return get_agent("codex").is_available()
        if provider == "gemini":
            from ai4science.llm import gemini
            return gemini.is_available()
    except Exception:
        return None
    return None


def _finish_own(provider: str, auth: str, api_key: Optional[str]) -> None:
    try:
        user_cfg.login_own(provider, auth, api_key)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[green]✓ Logged in[/green] with your own [bold]{provider}[/bold] "
                  f"via [bold]{auth}[/bold]. No PWM is spent — usage is on your account.")
    r = _reachable(provider, auth)
    if r is True:
        console.print("[dim]  reachable on this server ✓[/dim]")
    elif r is False:
        hint = {"anthropic": "npm i -g @anthropic-ai/claude-code && claude login",
                "openai": "npm i -g @openai/codex && codex login"}.get(provider, "")
        console.print(f"[yellow]  not reachable yet[/yellow]"
                      + (f" — {hint}" if hint else ""))
    elif auth == "api_key":
        console.print("[dim]  key stored (chmod 600); not test-called.[/dim]")
    if provider in ("kimi", "qwen"):
        console.print(f"[yellow]  note: {provider} backend isn't wired into routing yet "
                      "(stored as your preference).[/yellow]")


def login(
    provider: Optional[str] = typer.Option(
        None, "--provider", help="anthropic | openai | gemini | kimi | qwen"),
    auth: Optional[str] = typer.Option(
        None, "--auth", help="subscription | api-key"),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="API key (with --auth api-key)."),
    wallet: bool = typer.Option(
        False, "--wallet", help="Use the local hot-key PWM wallet instead of your own LLM."),
    pwm: bool = typer.Option(
        False, "--pwm", help="Log in to your physicsworldmodel.org account "
                             "(browser approval; token only, never a private key)."),
    base: Optional[str] = typer.Option(
        None, "--base", help="Backend URL for --pwm (default https://physicsworldmodel.org)."),
) -> None:
    """Choose how to power AI4Science: your own LLM, or the PWM wallet."""
    # --- physicsworldmodel.org account (device flow) ---
    if pwm:
        _login_pwm(base)
        return

    # --- Wallet mode ---
    if wallet:
        user_cfg.login_wallet()
        w = local_wallet.ensure()
        console.print(f"[green]✓ Using the local hot-key PWM wallet.[/green]")
        console.print(f"  address: [magenta]{w['address']}[/magenta]")
        console.print(f"  balance: [bold]{local_wallet.balance():g} PWM[/bold]  "
                      "[dim](earn by mining / contributing; spent per use)[/dim]")
        return

    # --- Own-LLM mode, scriptable (flags) ---
    if provider:
        auth = (auth or "subscription").replace("-", "_")
        _finish_own(provider.lower(), auth, api_key)
        return

    # --- Interactive ---
    if not sys.stdin.isatty():
        console.print("Usage (non-interactive):")
        console.print("  ai4science login --provider anthropic --auth subscription")
        console.print("  ai4science login --provider openai --auth api-key --api-key sk-…")
        console.print("  ai4science login --wallet")
        raise typer.Exit(2)

    console.print("\n[bold]How do you want to power AI4Science?[/bold]")
    console.print("  [cyan]1[/cyan]. Your own LLM (subscription or API key) — no PWM spent")
    console.print("  [cyan]2[/cyan]. Wallet / PWM — pay per use from your local hot-key wallet")
    console.print("  [cyan]3[/cyan]. physicsworldmodel.org account — pay PWM from your site "
                  "balance (browser login; no private key)")
    choice = typer.prompt("Choose [1/2/3]", default="1").strip()
    if choice == "2":
        login(wallet=True)
        return
    if choice == "3":
        _login_pwm(None)
        return

    console.print("\n[bold]Pick a provider:[/bold]")
    for i, p in enumerate(user_cfg.PROVIDERS, 1):
        console.print(f"  [cyan]{i}[/cyan]. {p}")
    sel = typer.prompt("Provider [1-5 or name]").strip().lower()
    if sel.isdigit() and 1 <= int(sel) <= len(user_cfg.PROVIDERS):
        provider = user_cfg.PROVIDERS[int(sel) - 1]
    else:
        provider = sel
    auth = typer.prompt("Auth [subscription/api-key]", default="subscription").replace("-", "_")
    key = None
    if auth == "api_key":
        key = typer.prompt(f"{provider} API key", hide_input=True).strip()
    _finish_own(provider, auth, key)


def whoami() -> None:
    """Show how the agent is currently powered."""
    cfg = user_cfg.load()
    acct = pwm_account.load()
    if not cfg and not acct:
        console.print("[dim]Not logged in.[/dim] Run [cyan]ai4science login[/cyan].")
        return
    if not cfg:
        console.print("[dim]No LLM login (run [/dim][cyan]ai4science login[/cyan][dim] "
                      "to pick a provider).[/dim]")
    elif cfg.get("power") == "wallet":
        console.print("[bold]Powered by:[/bold] local hot-key PWM wallet")
        console.print(f"  address: [magenta]{local_wallet.address()}[/magenta]")
        console.print(f"  balance: [bold]{local_wallet.balance():g} PWM[/bold]")
    else:
        console.print(f"[bold]Powered by:[/bold] your own [bold]{cfg.get('provider')}[/bold] "
                      f"via {cfg.get('auth')}"
                      + ("  [dim](API key stored)[/dim]" if cfg.get("api_key_set") else ""))
    if acct:
        who = acct.get("email") or f"user #{acct.get('user_id')}"
        console.print(f"[bold]PWM account:[/bold] {who} [dim]({acct.get('base')})[/dim]"
                      + (f"  wallet [magenta]{acct['wallet']}[/magenta]" if acct.get("wallet") else ""))
    console.print(f"[dim]Source preference: {user_cfg.preference()} "
                  "(change with [/dim][cyan]ai4science prefer <user|wallet|provider_id>[/cyan][dim])[/dim]")


def prefer(
    value: str = typer.Argument(..., help="user | wallet | <provider_id>"),
) -> None:
    """Set which credential source the agent prefers (point 11)."""
    user_cfg.set_preference(value)
    console.print(f"[green]✓ Preference set:[/green] [bold]{value}[/bold]")
    if value == "user":
        console.print("[dim]Your own login/keys are used first; wallet providers fall back.[/dim]")
    elif value == "wallet":
        console.print("[dim]Wallet providers are used first.[/dim]")
    else:
        console.print(f"[dim]Pinned to wallet provider '{value}' where it serves the backend; "
                      "otherwise user-first.[/dim]")


def logout() -> None:
    """Clear the login (keys + wallet are left on disk; delete them manually)."""
    user_cfg.logout()
    if pwm_account.clear():
        console.print("[green]✓ PWM account token removed.[/green] "
                      "[dim](revoke server-side too: Account → API key)[/dim]")
    console.print("[green]✓ Logged out.[/green] "
                  "[dim](API keys / wallet files are kept; remove manually if desired.)[/dim]")
