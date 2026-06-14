"""ai4science plugins test — embed a plug-in into an agent + login/PWM gating."""
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai4science.commands import plugins as pcmd
from ai4science.harness.agents import registry

runner = CliRunner()

TOOL = {"kind": "tool", "name": "denoise-x", "title": "Denoise X", "description": "d",
        "mcp_servers": [{"name": "dn"}], "wallet": "0xtool"}
AGENT = {"kind": "agent", "name": "spec-agent", "title": "Spec Agent", "description": "d",
         "tier": "science", "capabilities": ["pwm-data"], "wallet": "0xagent"}
BAD = {"kind": "agent", "name": "nope"}   # missing title/description


def _write(d, name, obj):
    p = Path(d) / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


@pytest.fixture
def env(monkeypatch):
    calls = []
    monkeypatch.setattr(pcmd, "_launch_chat", lambda **k: calls.append(k))
    monkeypatch.setattr(pcmd, "_logged_in", lambda: "tester@acct")  # logged in by default
    for v in ("AI4SCIENCE_PLUGINS_DIR", "AI4SCIENCE_PWM_GATE", "PWM_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    yield calls
    for v in ("AI4SCIENCE_PLUGINS_DIR", "AI4SCIENCE_PWM_GATE"):
        os.environ.pop(v, None)
    registry.reload()   # restore builtins-only registry for other tests


# ── manifest resolution ─────────────────────────────────────────────────────

def test_resolve_manifest_file(tmp_path):
    data, kind, name = pcmd._resolve_manifest(_write(tmp_path, "t.json", TOOL))
    assert kind == "tool" and name == "denoise-x"


def test_resolve_invalid_raises(tmp_path):
    with pytest.raises(pcmd.TestPrepError):
        pcmd._resolve_manifest(_write(tmp_path, "b.json", BAD))


def test_resolve_missing_raises():
    with pytest.raises(pcmd.TestPrepError):
        pcmd._resolve_manifest("/no/such/file.json")


# ── login + PWM gating ──────────────────────────────────────────────────────

def test_requires_login(env, tmp_path, monkeypatch):
    monkeypatch.setattr(pcmd, "_logged_in", lambda: None)
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "t.json", TOOL)])
    assert res.exit_code == 1 and "login" in res.stdout.lower()
    assert env == []                              # chat never launched
    assert os.environ.get("AI4SCIENCE_PWM_GATE") != "1"


def test_logged_in_turns_gate_on(env, tmp_path):
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "t.json", TOOL)])
    assert res.exit_code == 0, res.stdout
    assert os.environ.get("AI4SCIENCE_PWM_GATE") == "1"
    assert "PWM gate ON" in res.stdout


def test_free_skips_login_and_gate(env, tmp_path, monkeypatch):
    monkeypatch.setattr(pcmd, "_logged_in", lambda: None)   # not logged in
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "t.json", TOOL), "--free"])
    assert res.exit_code == 0
    assert os.environ.get("AI4SCIENCE_PWM_GATE") != "1"


# ── embedding ───────────────────────────────────────────────────────────────

def test_tool_embeds_into_research(env, tmp_path):
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "t.json", TOOL)])
    assert res.exit_code == 0, res.stdout
    assert env and env[0]["into"] == "research"
    d = Path(os.environ["AI4SCIENCE_PLUGINS_DIR"])
    written = json.loads((d / "denoise-x.json").read_text())
    assert "research" in written["attach_to"]            # auto-attached to target
    assert "denoise-x" in registry.get("research").capabilities  # really embedded
    assert "isolated" in res.stdout


def test_into_other_agent(env, tmp_path):
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "t.json", TOOL), "--into", "paper"])
    assert res.exit_code == 0 and env[0]["into"] == "paper"
    d = Path(os.environ["AI4SCIENCE_PLUGINS_DIR"])
    assert "paper" in json.loads((d / "denoise-x.json").read_text())["attach_to"]


def test_agent_plugin_dispatchable_from_research(env, tmp_path):
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "a.json", AGENT)])
    assert res.exit_code == 0, res.stdout
    assert "spec-agent" in registry.dispatchable_targets(registry.get("research"))
    assert "dispatchable by" in res.stdout


def test_agent_into_open_main_warns(env, tmp_path):
    # claude-code is open-tier → cannot dispatch a science plug-in (moat). Warns,
    # still launches so the contributor sees the message.
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "a.json", AGENT),
                                   "--into", "claude-code"])
    assert res.exit_code == 0
    assert "not dispatchable" in res.stdout


def test_launch_receives_model_and_workspace(env, tmp_path):
    runner.invoke(pcmd.app, ["test", _write(tmp_path, "t.json", TOOL),
                             "--model", "opus", "-w", str(tmp_path)])
    assert env[0]["model"] == "opus" and env[0]["workspace"] == str(tmp_path)


def test_invalid_manifest_exits(env, tmp_path):
    res = runner.invoke(pcmd.app, ["test", _write(tmp_path, "b.json", BAD)])
    assert res.exit_code == 1 and env == []
