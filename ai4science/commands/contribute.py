"""ai4science contribute — open a template file in the user's editor.

Subcommands:
  ai4science contribute principle
  ai4science contribute spec
  ai4science contribute benchmark
  ai4science contribute solution
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Open a template for one of the four artifact types.")
console = Console()


def _drop_template(kind: str) -> Path:
    """Copy the template for *kind* into the cwd as <kind>.md (no overwrite)."""
    target = Path.cwd() / f"{kind}.md"
    if target.exists():
        console.print(f"[yellow]{target.name} already exists; opening it.[/yellow]")
        return target

    pkg_root = resources.files("ai4science")
    src = pkg_root / "templates" / f"{kind}.template.md"
    contents = src.read_text(encoding="utf-8")
    target.write_text(contents, encoding="utf-8")
    console.print(f"[green]✓[/green] Created [bold]{target.name}[/bold] from template.")
    return target


def _open_in_editor(path: Path) -> None:
    """Hand off to $EDITOR. If $EDITOR is unset we just tell the user where it is."""
    import os, shutil, subprocess
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        console.print(
            f"[yellow]No $EDITOR set.[/yellow] Edit [bold]{path}[/bold] in your "
            "preferred editor, then run [cyan]ai4science validate[/cyan]."
        )
        return
    if shutil.which(editor.split()[0]) is None:
        console.print(f"[yellow]$EDITOR={editor!r} not found on PATH.[/yellow] Edit {path} manually.")
        return
    try:
        subprocess.run([editor, str(path)], check=False)
    except (OSError, subprocess.SubprocessError) as e:
        console.print(f"[yellow]Could not launch editor:[/yellow] {e}. Edit {path} manually.")


@app.command("principle")
def principle() -> None:
    """Create or open principle.md from the template."""
    path = _drop_template("principle")
    _open_in_editor(path)


@app.command("spec")
def spec() -> None:
    """Create or open spec.md from the template."""
    path = _drop_template("spec")
    _open_in_editor(path)


@app.command("benchmark")
def benchmark() -> None:
    """Create or open benchmark.md from the template."""
    path = _drop_template("benchmark")
    _open_in_editor(path)


@app.command("solution")
def solution() -> None:
    """Create or open solution.md from the template."""
    path = _drop_template("solution")
    _open_in_editor(path)
