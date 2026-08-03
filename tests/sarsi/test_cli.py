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


def test_main_dispatches_sarsi_as_a_subcommand_not_a_prompt(monkeypatch):
    """`main()` routes unknown first tokens to the LLM. A subcommand that is
    registered on the Typer app but missing from main()'s dispatch sets works
    under CliRunner and burns an LLM call in the real CLI."""
    import sys

    from ai4science import cli

    routed = []
    monkeypatch.setattr(cli, "_route_prompt",
                        lambda *a, **k: routed.append(a) or 0)
    monkeypatch.setattr(sys, "argv", ["ai4science", "sarsi", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert routed == []                    # not sent to the LLM …
    assert exc.value.code == 0             # … and not refused as unknown either


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


def test_ask_reaches_the_named_agent(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "work", "triage my mail"])
    assert result.exit_code == 0
    assert "work" in result.output


def test_ask_prints_the_reply_verbatim(isolated):
    """The agent's own words are data, not markup. `[abraham]` is a name the
    owner must see, and rich would eat it as a style tag."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "abraham", "what is on today?"])
    assert "[abraham]" in result.output


def test_ask_records_on_the_same_log_the_bot_writes_to(isolated):
    """A surface is a door, not a scope."""
    from ai4science.harness.agents.sarsi import ownerlog
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "ask", "work", "use the staging host"])
    config = reg.load()
    entries = ownerlog.said(config, config.agents["work"])
    assert [(e["text"], e["surface"]) for e in entries] == [
        ("use the staging host", "cli")]


def test_ask_an_unknown_agent_refuses_and_names_the_known_ones(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "ghost", "hello"])
    assert result.exit_code != 0
    assert "abraham" in result.output          # tells you what you could have said


def test_the_manager_says_it_does_not_drive_sessions(isolated):
    """§1, reported rather than assumed."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "sarsi-machine", "run my tests"])
    assert "do not drive" in result.output.lower() or "not drive" in result.output.lower()


def test_gateway_with_no_tokens_reports_rather_than_polling_nothing(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "gateway", "--passes", "1"])
    assert result.exit_code != 0
    assert "token" in result.output.lower()


def test_init_twice_refuses(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "init", "--owner-id", "999"])
    assert result.exit_code != 0
    assert reg.load().owner_id == "7007143162"          # the first one stands
