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
    assert payment_gate("shallow", None, "k")[0] is True


def test_payment_gate_deep_free_without_gate():
    # deep is free when there's no gate (not logged in) or the gate is disabled
    assert payment_gate("deep", None, "k")[0] is True

    class _Off:
        enabled = False

    assert payment_gate("deep", _Off(), "k")[0] is True


def test_payment_gate_deep_denied_when_charge_fails():
    from ai4science.harness.paper_tools import PAPER_DEEP_COST

    class _Gate:
        enabled = True

        def __init__(self):
            self.calls = []

        def charge(self, amount, wallet, reason, idem):
            self.calls.append((amount, reason))
            return False, "insufficient PWM"

    g = _Gate()
    ok, reason = payment_gate("deep", g, "k")
    assert ok is False and "pwm" in reason.lower()
    assert g.calls[0][0] == PAPER_DEEP_COST


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
    seen = {}
    def fake_run_panel(**kw):
        seen["depth"] = kw["depth"]
        return _fake_bundle()
    monkeypatch.setattr(paper_tools, "run_panel", fake_run_panel)
    monkeypatch.setattr(paper_tools, "adapter_for", lambda b: object())

    class _Gate:                       # enabled gate whose charge fails
        enabled = True

        def charge(self, *a):
            return False, "insufficient PWM"

    tools = {t.name: t for t in build_paper_tools(
        brand_provider=lambda: ("gemini", "m"),
        research_tools_provider=lambda: [],
        gate_provider=lambda: _Gate())}
    out = tools["paper_review"].func(tmp_path, path="p.md", depth="deep")
    assert seen["depth"] == "shallow"
    assert "shallow" in out.lower() or "accept" in out


def test_paper_review_bad_path(tmp_path):
    out = _tools()["paper_review"].func(tmp_path, path="../escape.md", depth="shallow")
    assert "[paper error]" in out


def test_paper_review_tool_is_non_mutating():
    assert _tools()["paper_review"].mutating is False


def test_paper_review_absolute_path_rejected(tmp_path):
    out = _tools()["paper_review"].func(tmp_path, path="/etc/passwd", depth="shallow")
    assert "[paper error]" in out
