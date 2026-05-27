"""ai4science submit — v0.1 is dry-run only; do not connect to production."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def submit(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w",
                                    help="Workspace directory."),
    dry_run: bool = typer.Option(True, "--dry-run/--for-real",
                                  help="v0.1 enforces dry-run; --for-real is rejected."),
) -> None:
    """Simulate a submission to the PWM registry. v0.1 does NOT connect to a remote."""
    if not dry_run:
        console.print(
            "[red]v0.1 only supports --dry-run.[/red] Live submission requires the founders-"
            "multisig flow, which is intentionally NOT in this CLI."
        )
        raise typer.Exit(2)

    workspace = workspace.resolve()
    console.print(f"[bold]Dry-run submission from[/bold] {workspace}\n")

    # Look for the most recent package zip + manifest in cwd.
    zips: List[Path] = sorted(workspace.glob("ai4science_submission_*.zip"))
    manifests: List[Path] = sorted(workspace.glob("ai4science_submission_*.manifest.json"))

    table = Table(title="What would be submitted", show_lines=False)
    table.add_column("Item", style="cyan")
    table.add_column("Status")

    if zips:
        table.add_row("package zip", f"[green]{zips[-1].name}[/green]")
    else:
        table.add_row("package zip", "[red]missing — run `ai4science package` first[/red]")

    if manifests:
        latest = manifests[-1]
        try:
            cert = json.loads(latest.read_text(encoding="utf-8"))
            table.add_row("manifest", f"[green]{latest.name}[/green]")
            table.add_row("certificate_hash", cert.get("certificate_hash", "—"))
            table.add_row("file count", str(len(cert.get("files", []))))
            table.add_row("promotion_status", cert.get("promotion_status", "—"))
        except json.JSONDecodeError:
            table.add_row("manifest", "[red]malformed manifest JSON[/red]")
    else:
        table.add_row("manifest", "[red]missing[/red]")

    console.print(table)
    console.print(
        "\n[yellow]Dry-run only.[/yellow] v0.1 stops here. To actually publish to the PWM "
        "testnet, follow [cyan]docs/SUBMITTING.md[/cyan] (or the future "
        "[cyan]ai4science submit --for-real[/cyan] once cryptographic signing is wired)."
    )

    if not zips or not manifests:
        raise typer.Exit(1)
