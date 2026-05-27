"""ai4science judge — CLI entry to the CASSI judge (and future domain judges)."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ai4science.judge.cassi import judge_cassi

app = typer.Typer(help="Run the deterministic Physics Judge on a submission.")
console = Console()


@app.command("cassi")
def cassi(
    submission: str = typer.Option(".", "--submission", "-s",
                                    help="Path to the contribution workspace."),
) -> None:
    """Run the CASSI Physics Judge (S1-S4) on a workspace."""
    path = Path(submission)
    report = judge_cassi(path)

    table = Table(title=f"CASSI Judge — {report['submission_id']}", show_lines=True)
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Message")

    table.add_row("S1 (finite spec)",       _color(report["s1_status"]), report["s1_message"])
    table.add_row("S2 (Hadamard)",          _color(report["s2_status"]), report["s2_message"])
    table.add_row("S3 (benchmark)",         _color(report["s3_status"]), report["s3_message"])
    table.add_row("S4 (overall)",           _color(report["s4_status"]), "")
    for name, sub in report["s4_checks"].items():
        table.add_row(f"  S4.{name}",       _color(sub["status"]),       sub["message"])

    console.print(table)
    console.print(f"\n[bold]Silent failure detected:[/bold] {report['silent_failure']}")
    console.print(f"[bold]Final decision:[/bold] {_color(report['final_decision'])}")
    console.print(f"[dim]Report written to[/dim] {path.resolve() / 'reports' / 'judge_report.json'}")

    if report["final_decision"] == "fail":
        raise typer.Exit(1)


def _color(status: str) -> str:
    return {
        "pass":          "[green]pass[/green]",
        "fail":          "[red]fail[/red]",
        "warning":       "[yellow]warning[/yellow]",
        "not_available": "[dim]not_available[/dim]",
        "needs_review":  "[yellow]needs_review[/yellow]",
    }.get(status, status)
