"""Tests for `ai4science validate`."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ai4science.cli import app

runner = CliRunner()


def _init_cassi(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init", "demo"])
    assert r.exit_code == 0, r.output
    return tmp_path / "demo"


def test_valid_cassi_example_passes(tmp_path: Path, monkeypatch):
    ws = _init_cassi(tmp_path, monkeypatch)
    r = runner.invoke(app, ["validate", "--workspace", str(ws)])
    assert r.exit_code == 0, r.output
    assert "ok" in r.output.lower()


def test_missing_required_field_fails(tmp_path: Path, monkeypatch):
    ws = _init_cassi(tmp_path, monkeypatch)
    # Surgically remove a required field from spec.md
    spec = ws / "spec.md"
    txt = spec.read_text()
    # Remove the 'tolerance_epsilon' line — required field.
    bad = "\n".join(line for line in txt.splitlines()
                    if not line.strip().startswith("tolerance_epsilon"))
    spec.write_text(bad)
    r = runner.invoke(app, ["validate", "--workspace", str(ws)])
    assert r.exit_code == 1, r.output


def test_broken_yaml_fails(tmp_path: Path, monkeypatch):
    ws = _init_cassi(tmp_path, monkeypatch)
    # Replace spec.md with intentionally broken YAML (unterminated front matter).
    (ws / "spec.md").write_text("---\nname: oops\n")  # no closing '---'
    r = runner.invoke(app, ["validate", "--workspace", str(ws)])
    assert r.exit_code == 1, r.output


def test_validate_with_no_artifacts_exits_2(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    r = runner.invoke(app, ["validate", "--workspace", str(empty)])
    assert r.exit_code == 2, r.output
