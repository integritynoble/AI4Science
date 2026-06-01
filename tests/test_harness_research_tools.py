from __future__ import annotations

from pathlib import Path
from ai4science.harness import research_tools, pwm_data


def test_research_tools_present():
    names = {t.name for t in research_tools.research_tools()}
    assert {"pwm_principles", "pwm_principle", "pwm_benchmarks",
            "pwm_solutions", "pwm_overview"}.issubset(names)
    assert all(t.mutating is False for t in research_tools.research_tools())


def test_pwm_solutions_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(pwm_data, "solutions",
                        lambda bid: [{"label": "MST-L", "score_q": 0.95}])
    tool = {t.name: t for t in research_tools.research_tools()}["pwm_solutions"]
    out = tool.func(tmp_path, benchmark_id="L3-003")
    assert "MST-L" in out and "0.95" in out


def test_pwm_tool_error_is_caught(monkeypatch, tmp_path):
    def _boom():
        raise RuntimeError("net down")
    monkeypatch.setattr(pwm_data, "principles", _boom)
    tool = {t.name: t for t in research_tools.research_tools()}["pwm_principles"]
    out = tool.func(tmp_path)
    assert "error" in out.lower() and "net down" in out
