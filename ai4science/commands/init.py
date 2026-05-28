"""ai4science init — create a new contribution workspace."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import typer
import yaml
from rich.console import Console

console = Console()


def init(
    project_name: str = typer.Argument(..., help="Directory name to create."),
    seed: str = typer.Option(
        "cassi",
        "--seed",
        help="Which example to seed the workspace with (currently: 'cassi' or 'blank').",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite if the directory exists."),
) -> None:
    """Create a contribution workspace pre-populated with the four artifact files."""
    target = Path(project_name).resolve()

    if target.exists() and any(target.iterdir()) and not force:
        console.print(f"[red]Refusing to overwrite non-empty[/red] {target}")
        console.print("Use [cyan]--force[/cyan] to overwrite, or pick a new name.")
        raise typer.Exit(2)

    target.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "code", "results", "reports", ".ai4science"):
        (target / sub).mkdir(exist_ok=True)

    # Pick the source: example workspace or blank templates.
    if seed == "cassi":
        _seed_from_package("examples/cassi", target)
        source_label = "CASSI example"
    elif seed == "blank":
        _seed_blank(target)
        source_label = "blank templates"
    else:
        console.print(f"[red]Unknown --seed value:[/red] {seed!r}. Use 'cassi' or 'blank'.")
        raise typer.Exit(2)

    # Write the per-workspace config.
    cfg = {
        "schema_version": "0.1",
        "seed": seed,
        "judge_domain": "cassi" if seed == "cassi" else "generic",
        "agent_provider": "none",  # 'none' | 'claude' | 'codex'
    }
    (target / ".ai4science" / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))

    console.print(f"[green]✓[/green] Created [bold]{target.name}/[/bold] from {source_label}.")
    console.print(f"\nNext: [cyan]cd {target.name}/  &&  ai4science validate[/cyan]")


def _seed_from_package(rel_dir: str, target: Path) -> None:
    """Copy an example dir from ai4science/<rel_dir>/ into the new workspace."""
    pkg_root = resources.files("ai4science")
    src = pkg_root / rel_dir
    for fname in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
        contents = (src / fname).read_text(encoding="utf-8")
        (target / fname).write_text(contents, encoding="utf-8")
    # Copy the reference solver code/ if the example ships one, so the full
    # generate → solve → judge pipeline works out of the box.
    code_src = src / "code"
    if code_src.is_dir():
        code_dst = target / "code"
        code_dst.mkdir(exist_ok=True)
        for entry in code_src.iterdir():
            if entry.name.endswith(".py"):
                (code_dst / entry.name).write_text(
                    entry.read_text(encoding="utf-8"), encoding="utf-8")


def _seed_blank(target: Path) -> None:
    """Copy template stubs (which contain TODOs)."""
    pkg_root = resources.files("ai4science")
    tpl_dir = pkg_root / "templates"
    pairs = [
        ("principle.template.md", "principle.md"),
        ("spec.template.md",      "spec.md"),
        ("benchmark.template.md", "benchmark.md"),
        ("solution.template.md",  "solution.md"),
    ]
    for src_name, dest_name in pairs:
        contents = (tpl_dir / src_name).read_text(encoding="utf-8")
        (target / dest_name).write_text(contents, encoding="utf-8")
