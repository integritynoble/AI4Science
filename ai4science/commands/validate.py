"""ai4science validate — parse YAML front matter and validate against Pydantic schemas."""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ai4science.discovery import all_artifact_files, missing_canonical
from ai4science.schemas import SCHEMA_BY_TYPE, parse_front_matter

console = Console()


def validate(
    workspace: Path = typer.Option(
        Path("."),
        "--workspace",
        "-w",
        help="Workspace directory. Defaults to current working dir.",
    ),
) -> None:
    """Discover and validate every artifact .md (by artifact_type front matter).

    Multi-tier aware: benchmark.md AND benchmark_t2.md (etc.) are both
    picked up, as is any extra solution file. Discovery is content-based,
    so a README.md without front matter is ignored.
    """
    workspace = workspace.resolve()
    table = Table(title=f"Validation: {workspace.name}", show_lines=True)
    table.add_column("File", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Status")
    table.add_column("Missing / errors", style="yellow")
    table.add_column("Warnings", style="dim")

    discovered = all_artifact_files(workspace)

    # A canonical-named file that EXISTS but didn't classify (broken YAML /
    # bad artifact_type) must still be flagged — not silently skipped.
    discovered_resolved = {p.resolve() for p in discovered}
    problem_files: List[Path] = []
    for fname in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
        p = workspace / fname
        if p.exists() and p.resolve() not in discovered_resolved:
            problem_files.append(p)

    to_check = discovered + problem_files
    overall_ok = True

    for path in to_check:
        status, atype, missing_or_errors, warnings = _validate_one(path)
        if status != "[green]ok[/green]":
            overall_ok = False
        # Show path relative to workspace so subdir layouts read cleanly.
        rel = path.relative_to(workspace) if path.is_relative_to(workspace) else path
        table.add_row(str(rel), atype, status, missing_or_errors, warnings)

    # Hint rows for canonical artifacts that aren't present at all
    # (genuinely absent — not the broken ones we just flagged above).
    problem_names = {p.name for p in problem_files}
    for fname in missing_canonical(workspace):
        if fname not in problem_names:
            table.add_row(fname, "-", "[dim]absent[/dim]", "", "")

    console.print(table)

    if not to_check:
        console.print(
            "[red]No artifact files found.[/red] Run [cyan]ai4science init <name>[/cyan] "
            "or one of the [cyan]ai4science contribute[/cyan] subcommands."
        )
        raise typer.Exit(2)

    if not overall_ok:
        raise typer.Exit(1)


def _validate_one(path: Path) -> Tuple[str, str, str, str]:
    """Return (status_text, artifact_type, missing_or_errors, warnings)."""
    data, error = parse_front_matter(path)
    if error is not None:
        return f"[red]invalid YAML[/red]", "-", error, ""

    atype = data.get("artifact_type", "")
    if atype not in SCHEMA_BY_TYPE:
        return (
            "[red]bad artifact_type[/red]",
            str(atype) or "-",
            f"artifact_type must be one of: {sorted(SCHEMA_BY_TYPE)}",
            "",
        )

    schema = SCHEMA_BY_TYPE[atype]
    try:
        schema.model_validate(data)
    except ValidationError as e:
        problems: List[str] = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            problems.append(f"{loc}: {err['msg']}")
        return "[red]fail[/red]", atype, "; ".join(problems), ""

    # Heuristic warnings (non-fatal): unresolved TODOs in the body.
    warnings: List[str] = []
    body_text = path.read_text(encoding="utf-8")
    if "TODO" in body_text:
        warnings.append(f"{body_text.count('TODO')} TODOs still in body")

    warning_text = "; ".join(warnings)
    return "[green]ok[/green]", atype, "", warning_text
