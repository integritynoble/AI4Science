from __future__ import annotations

from ai4science.harness import mcp_pwm


def test_pwm_tools_registered():
    tools = {t.name: t for t in mcp_pwm.pwm_tools()}
    assert "pwm_status" in tools and "pwm_judge_cassi" in tools
    assert "pwm_validate" in tools and "pwm_lookup_artifact" in tools
    assert tools["pwm_status"].mutating is False


def test_pwm_status_runs(tmp_path):
    tools = {t.name: t for t in mcp_pwm.pwm_tools()}
    out = tools["pwm_status"].func(tmp_path)   # returns the extracted text (a JSON string)
    assert isinstance(out, str) and "{" in out and "artifacts" in out


def test_pwm_error_is_caught(tmp_path, monkeypatch):
    # if a pwm coroutine raises, the wrapper returns an error string, not a crash
    import ai4science.agents.mcp_pwm as pwm_mod
    async def _boom(args):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(pwm_mod, "pwm_validate", _boom)
    tools = {t.name: t for t in mcp_pwm.pwm_tools()}
    out = tools["pwm_validate"].func(tmp_path)
    assert "error" in out.lower() and "kaboom" in out
