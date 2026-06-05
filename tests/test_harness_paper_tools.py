import os
import pytest
from ai4science.harness import paper_tools
from ai4science.harness.paper_tools import paper_tools as build_paper_tools, payment_gate
from ai4science.harness.paper_bundle import (ReviewBundle, ReviewerReview, ReviewerScores)


def _fake_bundle():
    r = ReviewerReview("generalist", "s", ["a"], ["b"], ["q"], ReviewerScores(3, 3, 3), 8, 4)
    return ReviewBundle(paper={"title": "T", "source_path": "T.md"}, depth="shallow",
                        reviews=[r], meta_review=None, decision="accept",
                        aggregate={"mean_rating": 8.0}, model="m", backend="g",
                        created_at="2026-06-05T00:00:00")


def _tools(brand=("gemini", "m")):
    return {t.name: t for t in build_paper_tools(
        brand_provider=lambda: brand,
        research_tools_provider=lambda: [])}


def test_payment_gate_shallow_always_allowed():
    assert payment_gate("shallow")[0] is True


def test_payment_gate_deep_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_PAPER_DEEP", "0")
    ok, reason = payment_gate("deep")
    assert ok is False and "pwm" in reason.lower()


def test_paper_review_tool_runs_and_writes(tmp_path, monkeypatch):
    (tmp_path / "p.md").write_text("# Paper\nbody")
    captured = {}
    def fake_run_panel(**kw):
        captured.update(kw)
        return _fake_bundle()
    monkeypatch.setattr(paper_tools, "run_panel", fake_run_panel)
    monkeypatch.setattr(paper_tools, "adapter_for", lambda b: object())
    tool = _tools()["paper_review"]
    out = tool.func(tmp_path, path="p.md", depth="shallow")
    assert "accept" in out and "p-1.json" in out
    assert (tmp_path / ".ai4science" / "reviews" / "p-1.json").exists()
    assert captured["depth"] == "shallow"


def test_paper_review_deep_denied_falls_back_to_shallow(tmp_path, monkeypatch):
    (tmp_path / "p.md").write_text("# Paper\nbody")
    monkeypatch.setenv("AI4SCIENCE_PAPER_DEEP", "0")
    seen = {}
    def fake_run_panel(**kw):
        seen["depth"] = kw["depth"]
        return _fake_bundle()
    monkeypatch.setattr(paper_tools, "run_panel", fake_run_panel)
    monkeypatch.setattr(paper_tools, "adapter_for", lambda b: object())
    out = _tools()["paper_review"].func(tmp_path, path="p.md", depth="deep")
    assert seen["depth"] == "shallow"
    assert "shallow" in out.lower() or "accept" in out


def test_paper_review_bad_path(tmp_path):
    out = _tools()["paper_review"].func(tmp_path, path="../escape.md", depth="shallow")
    assert "[paper error]" in out


def test_paper_review_tool_is_non_mutating():
    assert _tools()["paper_review"].mutating is False
