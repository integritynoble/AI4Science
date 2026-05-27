"""ai4science package — bundle the submission into a zip + certificate."""
from __future__ import annotations

import datetime as dt
import json
import zipfile
from pathlib import Path
from typing import List

import typer
from rich.console import Console

from ai4science.commands.validate import _validate_one
from ai4science.reports.certificate import build_certificate

console = Console()


def package(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w",
                                    help="Workspace directory."),
    output_dir: Path = typer.Option(Path("."), "--output", "-o",
                                     help="Where to write the .zip + manifest."),
    skip_validate: bool = typer.Option(False, "--skip-validate",
                                        help="Skip pre-package validation (not recommended)."),
) -> None:
    """Validate, hash, and zip the submission."""
    workspace = workspace.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not skip_validate:
        any_fatal = False
        for fname in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
            p = workspace / fname
            if not p.exists():
                console.print(f"[red]Missing artifact:[/red] {fname}")
                any_fatal = True
                continue
            status, _, errs, _ = _validate_one(p)
            if status != "[green]ok[/green]":
                console.print(f"[red]{fname} failed validation:[/red] {errs}")
                any_fatal = True
        if any_fatal:
            console.print("Fix the issues above (or rerun with --skip-validate).")
            raise typer.Exit(1)

    files: List[Path] = _collect_files(workspace)
    cert = build_certificate(files, workspace)

    # Write certificate next to the zip.
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_name = f"ai4science_submission_{ts}.zip"
    manifest_name = f"ai4science_submission_{ts}.manifest.json"

    zip_path = output_dir / zip_name
    manifest_path = output_dir / manifest_name

    manifest_path.write_text(
        json.dumps(cert, indent=2, sort_keys=False) + "\n", encoding="utf-8",
    )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.relative_to(workspace).as_posix())
        # Embed the certificate inside the zip for self-containment.
        zf.write(manifest_path, arcname="package_manifest.json")

    console.print(f"[green]✓[/green] Packaged {len(files)} files")
    console.print(f"  zip:      [cyan]{zip_path}[/cyan]")
    console.print(f"  manifest: [cyan]{manifest_path}[/cyan]")
    console.print(f"  certificate_hash: [bold]{cert['certificate_hash']}[/bold]")


def _collect_files(workspace: Path) -> List[Path]:
    """Choose which files go into the package."""
    items: List[Path] = []
    # The four artifact files (required if present)
    for fname in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
        p = workspace / fname
        if p.exists():
            items.append(p)
    # Recursively include code/, results/, reports/ — but skip binary blobs
    # the user almost certainly didn't mean to ship (>= 200 MB).
    MAX_PER_FILE = 200 * 1024 * 1024
    for sub in ("code", "results", "reports"):
        d = workspace / sub
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.stat().st_size <= MAX_PER_FILE:
                items.append(p)
    return items
