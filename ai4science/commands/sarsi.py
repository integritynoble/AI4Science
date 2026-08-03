"""`ai4science sarsi …` — the CLI door onto the sarsi agents.

Thin by design: every decision lives in `harness.agents.sarsi`, so the CLI and
the Telegram surface reach the same agent through the same code. A surface is a
door, not a scope.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ai4science.harness.agents.sarsi import admin, registry as reg

app = typer.Typer(help="sarsi worker agents on this machine.", no_args_is_help=True)
console = Console()


def _load() -> reg.Config:
    try:
        return reg.load()
    except reg.ConfigError as e:
        console.print(f"[red]registry error:[/red] {e}")
        raise typer.Exit(code=2)


@app.command("init", help="Write the seven-agent registry and create each agent's directories.")
def init(owner_id: str = typer.Option(..., "--owner-id",
                                      help="Your Telegram user id — the only id whose messages are honored.")) -> None:
    try:
        config = admin.init(owner_id=owner_id)
    except admin.AlreadyInitialised as e:
        console.print(f"[yellow]{e}[/yellow]")
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    console.print(f"wrote [cyan]{config.path}[/cyan] — {len(config.agents)} agents")
    console.print("add a bot token per agent, then: [cyan]ai4science sarsi agents --bindings[/cyan]")


@app.command("agents", help="List the agents, their ceilings, and (with --bindings) how each is reached.")
def agents(bindings: bool = typer.Option(False, "--bindings",
                                         help="Show each agent's channel bindings.")) -> None:
    config = _load()
    table = Table(title="sarsi agents", show_lines=False)
    table.add_column("Agent", style="cyan")
    table.add_column("Role")
    table.add_column("Drives sessions")
    table.add_column("Ceiling")
    table.add_column("Telegram")
    rows = admin.agent_rows(config)
    for row in rows:
        # the invariant, shown rather than assumed: the manager may not execute
        drives = "[green]yes[/green]" if row["drives_sessions"] else "[yellow]no[/yellow]"
        table.add_row(row["id"], row["role"], drives, row["ceiling"], row["telegram"])
    console.print(table)
    if bindings:
        # printed as lines rather than a table column: a wrapped cell can split
        # `telegram:work` across two rows, and a binding you cannot read is a
        # binding you cannot check.
        console.print("\nbindings — how each agent is reached:")
        width = max(len(r["id"]) for r in rows)
        for row in rows:
            reached = " ".join(row["bindings"]) or "[yellow]unreachable[/yellow]"
            console.print(f"  {row['id']:<{width}}  {reached}", highlight=False)


@app.command("ask", help="Say something to one agent from the CLI — the same door as its bot.")
def ask(agent_id: str = typer.Argument(..., help="Agent id, e.g. work"),
        text: str = typer.Argument(..., help="What to say")) -> None:
    from ai4science.harness.agents.sarsi import gateway, ownerlog, router

    config = _load()
    decision = router.decide(config, channel=router.CLI_CHANNEL, account_id=agent_id)
    if decision.dropped:
        console.print(f"[red]no agent {agent_id!r}[/red] — known: "
                      f"{', '.join(sorted(config.agents))}")
        raise typer.Exit(code=2)
    agent = decision.agent
    ownerlog.append(config, agent, text, surface=router.CLI_CHANNEL)
    reply = gateway.handle(agent=agent, text=text, surface=router.CLI_CHANNEL, chat_id="")
    # markup off: an agent's reply is data. `[abraham]` is a name, not a style.
    console.print(reply or "(no reply)", markup=False, highlight=False)


@app.command("gateway", help="Run the local daemon: poll every agent's bot and route what arrives.")
def gateway_cmd(passes: Optional[int] = typer.Option(None, "--passes",
                                                     help="Stop after N polls (default: run forever)."),
                interval: float = typer.Option(2.0, "--interval",
                                               help="Seconds between polls.")) -> None:
    from ai4science.harness.agents.sarsi import admin as _admin, gateway as gw

    config = _load()
    reachable = [r["id"] for r in _admin.agent_rows(config) if r["telegram"] == "configured"]
    if not reachable:
        console.print("[red]no agent has a bot token[/red] — nothing to poll.\n"
                      "set one with: [cyan]ai4science sarsi set-token <agent> <token>[/cyan]")
        raise typer.Exit(code=2)
    console.print(f"polling {len(reachable)} bot(s): {', '.join(reachable)}")
    try:
        gw.Gateway(config).run(interval=interval, passes=passes)
    except KeyboardInterrupt:
        console.print("stopped")


@app.command("set-token", help="Set one agent's Telegram bot token.")
def set_token(agent_id: str = typer.Argument(..., help="Agent id, e.g. work"),
              token: str = typer.Argument(..., help="Bot token from @BotFather")) -> None:
    _load()
    try:
        admin.set_bot_token(agent_id, token)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    console.print(f"token set for [cyan]{agent_id}[/cyan]")     # never echoed back
