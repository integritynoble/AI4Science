"""ai4science tools — install community protools from physicsworldmodel.org.

Protools are community-contributed MCP tool plug-ins (kind="tool") submitted via
physicsworldmodel.org/agents/contribute. They extend any AI4Science agent with new
capabilities — spectral algorithms, data loaders, compute bridges, domain adapters.

After pulling, a tool loads at the next agent start (no restart of the CLI needed).

Subcommands:
  list                 show the protool gallery (kind=tool only)
  pull <name>...       install named protool(s) into your plugins dir (or --all)
  installed            list locally installed tool plug-ins
  test <manifest>      embed a tool into an agent and open a test chat
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from ai4science.harness import transport
from ai4science.harness.agents import plugins as plugmod
from ai4science.commands.plugins import (
    DEFAULT_BASE, _base, _write_manifest,
    _resolve_manifest, _embed_manifest, _verify_embedded,
    _launch_chat, _logged_in, TestPrepError,
)

app = typer.Typer(help="Install community protools from physicsworldmodel.org.")
console = Console()


def _tool_gallery(base: str) -> list:
    """Fetch gallery and return only kind=tool entries."""
    data = transport.get_json(f"{base}/api/v1/plugins")
    all_plugins = data.get("plugins", []) if isinstance(data, dict) else []
    return [p for p in all_plugins if p.get("kind") == "tool"]


@app.command("list")
def list_cmd(
    base: Optional[str] = typer.Option(None, "--base",
        help=f"gallery base URL (default {DEFAULT_BASE})"),
) -> None:
    """List community protools published on physicsworldmodel.org."""
    b = _base(base)
    try:
        rows = _tool_gallery(b)
    except Exception as exc:
        console.print(f"[red]Could not reach the gallery at {b}:[/red] {exc}")
        raise typer.Exit(1)
    if not rows:
        console.print(f"[yellow]No protools in the gallery at {b} yet.[/yellow]")
        console.print("[dim]Submit your own at "
                      "https://physicsworldmodel.org/agents/contribute[/dim]")
        return
    table = Table(title=f"Community protools — {b}", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Attaches to")
    table.add_column("Price", justify="right")
    table.add_column("Title")
    for p in rows:
        price = p.get("price_pwm") or 0
        table.add_row(
            p.get("name", "?"),
            p.get("target_agent") or "any",
            f"{price:g} PWM" if price else "free",
            p.get("title") or "",
        )
    console.print(table)
    console.print(
        "[dim]Install with:[/dim] ai4science tools pull <name>  "
        "[dim]| submit yours at physicsworldmodel.org/agents/contribute[/dim]"
    )


@app.command("installed")
def installed_cmd() -> None:
    """List protools installed in your local plugins dir."""
    d = plugmod.plugins_dir()
    _, tools, errors = plugmod.load_plugins(d)
    console.print(f"[bold]Plugins dir:[/bold] {d}")
    if not tools and not errors:
        console.print(
            "[yellow](no tools installed — "
            "pull some with `ai4science tools pull`)[/yellow]"
        )
        return
    for t in tools:
        console.print(f"  [green]tool[/green]  {t.name}")
    for e in errors:
        console.print(f"  [red]err[/red]   {e}")


@app.command("pull")
def pull_cmd(
    names: List[str] = typer.Argument(None, help="tool name(s) to install"),
    all_: bool = typer.Option(False, "--all", help="install every tool in the gallery"),
    base: Optional[str] = typer.Option(None, "--base"),
    directory: Optional[str] = typer.Option(None, "--dir",
        help="target plugins dir (default AI4SCIENCE_PLUGINS_DIR)"),
    force: bool = typer.Option(False, "--force",
        help="overwrite already-installed tools"),
) -> None:
    """Install protools from the physicsworldmodel.org gallery."""
    b = _base(base)
    d = Path(directory).expanduser() if directory else plugmod.plugins_dir()

    want = list(names or [])
    if all_:
        try:
            want = [p["name"] for p in _tool_gallery(b) if p.get("name")]
        except Exception as exc:
            console.print(f"[red]Could not reach gallery:[/red] {exc}")
            raise typer.Exit(1)
    if not want:
        console.print(
            "[red]Name a tool to pull[/red] (or pass --all). "
            "See `ai4science tools list`."
        )
        raise typer.Exit(2)

    console.print(f"[dim]Pulling tools from {b} into {d}[/dim]")
    installed = 0
    for name in want:
        try:
            manifest = transport.get_json(f"{b}/api/v1/plugins/{name}/manifest")
        except Exception as exc:
            console.print(f"[red]error[/red]  {name}: {exc}")
            continue
        if manifest.get("kind") != "tool":
            console.print(
                f"[yellow]skip[/yellow]  {name}: "
                f"not a tool (kind={manifest.get('kind')!r})"
            )
            continue
        status = _write_manifest(d, name, manifest, force=force)
        console.print("  " + status)
        if "installed" in status:
            installed += 1
    if installed:
        console.print(
            f"\n[green]Installed {installed} protool(s).[/green] "
            "They load on the next agent start "
            "([cyan]ai4science tools installed[/cyan] to verify)."
        )


@app.command("test")
def test_cmd(
    manifest: str = typer.Argument(
        ..., help="path to a manifest file, or an installed tool name"),
    into: str = typer.Option("research", "--into",
        help="agent to embed into (default research)"),
    free: bool = typer.Option(False, "--free",
        help="skip login + PWM gate (offline dev)"),
    workspace: str = typer.Option(".", "--workspace", "-w"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
) -> None:
    """Embed a protool into an agent and open a chat to test it.

    Loads ONLY this tool in an isolated temp dir — does not affect your installed
    plugins. Requires login (use --free for offline dev)."""
    try:
        data, kind, name = _resolve_manifest(manifest)
    except TestPrepError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    if kind != "tool":
        console.print(
            f"[yellow]⚠[/yellow] manifest kind is {kind!r}, not 'tool' — "
            "use `ai4science plugins test` for agents"
        )

    console.print(f"  [green]✓[/green] valid tool manifest [cyan]{name}[/cyan]")

    if not free:
        who = _logged_in()
        if not who:
            console.print(
                "[red]✗ Not logged in.[/red] "
                "Run `ai4science login` first (or --free for offline dev)."
            )
            raise typer.Exit(1)
        os.environ["AI4SCIENCE_PWM_GATE"] = "1"
        console.print(f"  [green]✓[/green] logged in as {who} — PWM gate ON")
    else:
        console.print("  [yellow]●[/yellow] --free: no login, PWM gate OFF")

    tmp = Path(tempfile.mkdtemp(prefix="ai4science-tooltest-"))
    _embed_manifest(data, kind, name, into, tmp)
    os.environ["AI4SCIENCE_PLUGINS_DIR"] = str(tmp)

    try:
        warns = _verify_embedded(name, kind, into)
    except TestPrepError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)

    console.print(
        f"  [green]✓[/green] tool embedded into [cyan]{into}[/cyan] "
        f"[dim](isolated: {tmp})[/dim]"
    )
    for w in warns:
        console.print(f"  [yellow]⚠[/yellow] {w}")
    console.print(
        f"  [green]→[/green] opening [cyan]{into}[/cyan] chat… "
        "test your tool, then /exit"
    )
    _launch_chat(into=into, workspace=workspace, model=model)
