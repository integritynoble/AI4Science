from __future__ import annotations

from pathlib import Path
from ai4science.harness import research_tools, pwm_data


def test_research_tools_present():
    names = {t.name for t in research_tools.research_tools()}
    assert {"pwm_search", "pwm_principles", "pwm_principle", "pwm_benchmarks",
            "pwm_benchmark", "pwm_solutions", "pwm_overview"}.issubset(names)


def test_pwm_search_filters(monkeypatch):
    monkeypatch.setattr(pwm_data, "principles", lambda: [
        {"id": "P1", "title": "CASSI snapshot spectral imaging", "domain": "optics"},
        {"id": "P2", "title": "Low-dose CT", "domain": "ct"}])
    monkeypatch.setattr(pwm_data, "benchmarks", lambda: [
        {"id": "B1", "title": "CASSI reconstruction PSNR"},
        {"id": "B2", "title": "MRI denoising"}])
    out = pwm_data.search("cassi")     # case-insensitive
    assert [p["id"] for p in out["principles"]] == ["P1"]
    assert [b["id"] for b in out["benchmarks"]] == ["B1"]
    # empty query returns everything (bounded)
    assert len(pwm_data.search("")["principles"]) == 2


def test_pwm_search_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(pwm_data, "principles", lambda: [{"id": "P1", "title": "MRI recon"}])
    monkeypatch.setattr(pwm_data, "benchmarks", lambda: [])
    tool = {t.name: t for t in research_tools.research_tools()}["pwm_search"]
    out = tool.func(tmp_path, query="mri")
    assert "P1" in out and "MRI recon" in out
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
