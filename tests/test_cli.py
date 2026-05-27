"""Smoke tests for the Typer CLI surface."""
from __future__ import annotations

from typer.testing import CliRunner

from ai4science.cli import app

runner = CliRunner()


def test_help_works():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ai4science" in result.output.lower()
    assert "init" in result.output
    assert "judge" in result.output
    assert "overseer" in result.output


def test_version_prints():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ai4science" in result.output


def test_contribute_subapp_help():
    result = runner.invoke(app, ["contribute", "--help"])
    assert result.exit_code == 0
    assert "principle" in result.output
    assert "spec" in result.output
    assert "benchmark" in result.output
    assert "solution" in result.output


def test_judge_subapp_help():
    result = runner.invoke(app, ["judge", "--help"])
    assert result.exit_code == 0
    assert "cassi" in result.output
