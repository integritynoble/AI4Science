"""The `ai4science sarsi …` command group — the CLI door onto the same agents.

The slice-0 observation lives here: `sarsi agents --bindings` shows seven
agents with isolated directories, and a broken registry refuses rather than
starting up half-wired.
"""
import json

import pytest
from typer.testing import CliRunner

from ai4science.cli import app
from ai4science.harness.agents.sarsi import admin, registry as reg

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


def test_sarsi_group_is_registered():
    result = runner.invoke(app, ["sarsi", "--help"])
    assert result.exit_code == 0
    assert "agents" in result.output


def test_init_then_agents_lists_all_seven(isolated):
    assert runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"]).exit_code == 0
    result = runner.invoke(app, ["sarsi", "agents"])
    assert result.exit_code == 0
    for name in ("sarsi-machine", "sarsi-worker", "work", "social",
                 "funding", "jobs", "abraham"):
        assert name in result.output


def test_agents_shows_bindings_when_asked(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "agents", "--bindings"])
    assert "telegram:work" in result.output and "cli:work" in result.output


def test_agents_never_prints_a_bot_token(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    admin.set_bot_token("work", "8541204756:AA-secret")
    result = runner.invoke(app, ["sarsi", "agents", "--bindings"])
    assert "AA-secret" not in result.output


def test_agents_on_a_broken_registry_reports_and_exits_nonzero(isolated):
    """A binding naming an unknown agent is a startup error, not a warning."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    path = isolated / "sarsi.json"
    raw = json.loads(path.read_text())
    raw["bindings"].append({"agentId": "ghost",
                            "match": {"channel": "cli", "accountId": "ghost"}})
    path.write_text(json.dumps(raw))
    result = runner.invoke(app, ["sarsi", "agents"])
    assert result.exit_code != 0
    assert "ghost" in result.output


def test_agents_before_init_says_how_to_fix_it(isolated):
    result = runner.invoke(app, ["sarsi", "agents"])
    assert result.exit_code != 0
    assert "init" in result.output


def test_init_twice_refuses(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "init", "--owner-id", "999"])
    assert result.exit_code != 0
    assert reg.load().owner_id == "7007143162"          # the first one stands
