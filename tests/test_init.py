"""Tests for `ai4science init`."""
from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from ai4science.cli import app

runner = CliRunner()


def test_init_creates_expected_files(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 0, result.output

    ws = tmp_path / "demo"
    assert (ws / "principle.md").exists()
    assert (ws / "spec.md").exists()
    assert (ws / "benchmark.md").exists()
    assert (ws / "solution.md").exists()
    for sub in ("data", "code", "results", "reports", ".ai4science"):
        assert (ws / sub).is_dir(), f"missing dir: {sub}"

    cfg = yaml.safe_load((ws / ".ai4science" / "config.yaml").read_text())
    assert cfg["seed"] == "cassi"
    assert cfg["judge_domain"] == "cassi"
    assert cfg["agent_provider"] == "none"


def test_init_refuses_existing_non_empty_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "junk.txt").write_text("hi")
    result = runner.invoke(app, ["init", "demo"])
    assert result.exit_code == 2
    assert "Refusing" in result.output


def test_init_blank_uses_templates(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "blank-demo", "--seed", "blank"])
    assert result.exit_code == 0, result.output
    txt = (tmp_path / "blank-demo" / "principle.md").read_text()
    assert "TODO" in txt
