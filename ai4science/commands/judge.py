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
    benchmark: str = typer.Option(None, "--benchmark", "-b",
                                   help="Which benchmark tier file to judge "
                                        "(e.g. benchmark_t2.md). Defaults to benchmark.md."),
) -> None:
    """Run the CASSI Physics Judge (S1-S4) on a workspace.

    Multi-tier: pass --benchmark benchmark_t2.md to judge a specific tier.
    The report is written to reports/judge_report_<stem>.json for non-default
    tiers (benchmark.md keeps the canonical judge_report.json)."""
    path = Path(submission)
    report = judge_cassi(path, benchmark=benchmark)

    bench_label = report.get("benchmark_file") or "benchmark.md"
    table = Table(title=f"CASSI Judge — {report['submission_id']} ({bench_label})",
                  show_lines=True)
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
    bf = report.get("benchmark_file")
    report_name = ("judge_report.json" if not bf or bf == "benchmark.md"
                   else f"judge_report_{Path(bf).stem}.json")
    console.print(f"\n[bold]Silent failure detected:[/bold] {report['silent_failure']}")
    console.print(f"[bold]Final decision:[/bold] {_color(report['final_decision'])}")
    console.print(f"[dim]Report written to[/dim] {path.resolve() / 'reports' / report_name}")

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
