"""Tests for the in-process PWM MCP server.

We test the tools by calling the wrapped functions directly with their
input-dict contract — this avoids needing a live SDK transport.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("claude_agent_sdk")

from ai4science.agents.mcp_pwm import (
    build_pwm_mcp_server, PWM_MCP_TOOL_NAMES,
    pwm_validate, pwm_judge_cassi, pwm_status, pwm_lookup_artifact,
)
from ai4science.cli import app

runner = CliRunner()


# ─── Server construction ──────────────────────────────────────────────


def test_server_constructs_without_error():
    srv = build_pwm_mcp_server()
    assert srv is not None
    # Sanity: server config has the expected name + 4 tools registered.
    assert srv.get("name") == "pwm" or srv["name"] == "pwm"


def test_advertised_tool_names_match_decorator_names():
    """The list we advertise to allowed_tools must match what we actually
    register, with the SDK's `mcp__<server>__<tool>` prefix scheme."""
    expected = {
        "mcp__pwm__pwm_validate",
        "mcp__pwm__pwm_judge_cassi",
        "mcp__pwm__pwm_status",
        "mcp__pwm__pwm_lookup_artifact",
    }
    assert set(PWM_MCP_TOOL_NAMES) == expected


# ─── Tool implementations (module-level coroutines) ───────────────────


def _make_demo_workspace(tmp_path: Path) -> Path:
    """Use the CLI `init` to create a working CASSI demo workspace."""
    import os
    cwd_before = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["init", "demo"])
        assert result.exit_code == 0, result.output
        return tmp_path / "demo"
    finally:
        os.chdir(cwd_before)


def test_pwm_status_reports_workspace_state(tmp_path):
    ws = _make_demo_workspace(tmp_path)
    result = asyncio.run(pwm_status({"workspace": str(ws)}))
    payload = json.loads(result["content"][0]["text"])
    assert payload["workspace"].endswith("demo")
    for f in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
        assert payload["artifacts"][f]["present"] is True
    assert payload["config"]["judge_domain"] == "cassi"


def test_pwm_validate_returns_ok_for_demo(tmp_path):
    ws = _make_demo_workspace(tmp_path)
    result = asyncio.run(pwm_validate({"workspace": str(ws)}))
    payload = json.loads(result["content"][0]["text"])
    assert payload["overall"] == "ok"
    for f in payload["files"]:
        assert f["status"] == "ok", f"{f['file']} failed validation: {f}"


def test_pwm_judge_cassi_writes_report(tmp_path):
    """Tool should be able to invoke the deterministic CASSI judge and
    return the same report it writes to reports/judge_report.json."""
    ws = _make_demo_workspace(tmp_path)
    result = asyncio.run(pwm_judge_cassi({"workspace": str(ws)}))
    payload = json.loads(result["content"][0]["text"])
    assert "s1_status" in payload
    assert "final_decision" in payload
    assert (ws / "reports" / "judge_report.json").exists()


def test_pwm_lookup_artifact_reads_principle(tmp_path):
    ws = _make_demo_workspace(tmp_path)
    result = asyncio.run(pwm_lookup_artifact(
        {"artifact": "principle", "workspace": str(ws)},
    ))
    payload = json.loads(result["content"][0]["text"])
    assert payload["front_matter"]["artifact_type"] == "principle"
    assert payload["parse_error"] is None
    assert "raw_text" in payload


def test_pwm_lookup_artifact_rejects_unknown(tmp_path):
    ws = _make_demo_workspace(tmp_path)
    result = asyncio.run(pwm_lookup_artifact(
        {"artifact": "ghosts", "workspace": str(ws)},
    ))
    assert result.get("isError") is True
    assert "unknown artifact" in result["content"][0]["text"]


def test_pwm_lookup_missing_file_is_error(tmp_path):
    """An empty workspace → lookup returns an isError result, not a crash."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = asyncio.run(pwm_lookup_artifact(
        {"artifact": "spec", "workspace": str(empty)},
    ))
    assert result.get("isError") is True
