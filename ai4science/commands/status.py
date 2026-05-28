"""ai4science status — print a workspace summary."""
from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from ai4science.schemas import parse_front_matter

console = Console()


def status(
    workspace: Path = typer.Option(
        Path("."), "--workspace", "-w", help="Workspace directory."
    ),
) -> None:
    """Show files present, artifact types detected, and report status."""
    workspace = workspace.resolve()
    console.print(f"\n[bold]Workspace:[/bold] {workspace}\n")

    # Config
    cfg_path = workspace / ".ai4science" / "config.yaml"
    if cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            cfg = {}
        console.print(f"[cyan]Config[/cyan]: judge_domain={cfg.get('judge_domain', '?')}, "
                      f"agent_provider={cfg.get('agent_provider', '?')}, seed={cfg.get('seed', '?')}")
    else:
        console.print("[dim]Config: (none — workspace not initialized via `ai4science init`)[/dim]")

    # Artifacts — discovered by artifact_type (multi-tier aware).
    from ai4science.discovery import all_artifact_files, missing_canonical
    artifacts_table = Table(title="Artifacts", show_lines=False)
    artifacts_table.add_column("File", style="cyan")
    artifacts_table.add_column("Present")
    artifacts_table.add_column("artifact_type")
    artifacts_table.add_column("name")

    discovered = all_artifact_files(workspace)
    for path in discovered:
        rel = path.relative_to(workspace) if path.is_relative_to(workspace) else path
        data, err = parse_front_matter(path)
        if err:
            artifacts_table.add_row(str(rel), "[red]✗ broken[/red]", "-", err)
        else:
            artifacts_table.add_row(
                str(rel), "[green]✓[/green]",
                str(data.get("artifact_type", "?")),
                str(data.get("name", "?")),
            )
    # Absent-canonical hints.
    for fname in missing_canonical(workspace):
        artifacts_table.add_row(fname, "[dim]✗[/dim]", "-", "-")
    console.print(artifacts_table)

    # Directories + reports
    dirs_table = Table(title="Workspace dirs", show_lines=False)
    dirs_table.add_column("Dir", style="cyan")
    dirs_table.add_column("Status")
    dirs_table.add_column("Entries")
    for d in ("data", "code", "results", "reports"):
        dpath = workspace / d
        if dpath.exists():
            n = len(list(dpath.iterdir()))
            dirs_table.add_row(d + "/", "[green]✓[/green]", str(n))
        else:
            dirs_table.add_row(d + "/", "[dim]✗[/dim]", "-")
    console.print(dirs_table)

    # Reports
    reports_dir = workspace / "reports"
    if reports_dir.exists():
        present_reports = [p.name for p in reports_dir.iterdir() if p.is_file()]
        if present_reports:
            console.print(f"[cyan]Reports present:[/cyan] {', '.join(sorted(present_reports))}")
        else:
            console.print("[dim]No reports yet. Run `ai4science judge cassi --submission .` "
                          "or `ai4science overseer review --submission .`[/dim]")
