"""ai4science register-agent — self-register a plug-in agent/tool you authored.

Posts to physicsworldmodel.org so your agent counts toward the **Developer
Winner** (after an admin approves it) and can earn usage emission. Uses your
`ai4science login` token. The contribution starts PENDING; approval activates it.
"""
from __future__ import annotations

import typer
from rich.console import Console

from ai4science import wallet

console = Console()

_TYPES = {"agent", "tool", "subagent"}
_PATH = "/api/v1/agent-pool/contributions/self"


def register_agent(
    name: str = typer.Option(..., "--name", "-n",
                             help="Agent slug, e.g. 'computational-imaging'."),
    ctype: str = typer.Option("agent", "--type", "-t",
                              help="Contribution type: agent | tool | subagent."),
    title: str = typer.Option("", "--title", help="Human-readable title."),
    ref: str = typer.Option("", "--ref",
                            help="Repo path or URL of the plug-in (e.g. harness/agents/<name>)."),
) -> None:
    """Self-register a plug-in agent/tool with physicsworldmodel.org (pending admin approval)."""
    ctype = ctype.strip().lower()
    if ctype not in _TYPES:
        console.print(f"[red]--type must be one of:[/red] {', '.join(sorted(_TYPES))}")
        raise typer.Exit(2)

    token = wallet.platform_token()
    if not token:
        console.print("[red]Not logged in.[/red] Run [bold]ai4science login[/bold] first "
                      "(or set PWM_TOKEN to your physicsworldmodel.org token).")
        raise typer.Exit(2)

    base = wallet.platform_base()
    body = {"agent_name": name, "ctype": ctype, "title": title or name,
            "artifact_ref": ref or None}
    try:
        status, resp = wallet.http_post(base, _PATH, token, body)
    except Exception as e:  # network / unexpected
        console.print(f"[red]Request failed:[/red] {e}")
        raise typer.Exit(1)

    if status == 200 and resp.get("success"):
        st = resp.get("status")
        agent = resp.get("agent_name")
        if resp.get("deduped"):
            console.print(f"[yellow]Already registered[/yellow] — '{agent}' "
                          f"({resp.get('ctype')}) is [bold]{st}[/bold].")
        else:
            console.print(f"[green]✓ Registered[/green] '{agent}' "
                          f"({resp.get('ctype')}) — status [bold]{st}[/bold].")
        console.print("It counts toward the [bold]Developer Winner[/bold] and can earn once an "
                      f"admin approves it. Track it at [cyan]{base}/developer-winner[/cyan]")
        return
    if status == 401:
        console.print("[red]Unauthorized.[/red] Your session may have expired — run "
                      "[bold]ai4science login[/bold] again.")
        raise typer.Exit(1)
    if status == 429:
        console.print(f"[red]Rate limited:[/red] {resp.get('detail', 'daily cap reached')}")
        raise typer.Exit(1)
    console.print(f"[red]Failed (HTTP {status}):[/red] {resp.get('detail', resp)}")
    raise typer.Exit(1)
