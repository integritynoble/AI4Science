# AI4Science/tests/test_registry_router.py
"""registry_router core: url, lineage, match, standard-gate (network-free)."""
from __future__ import annotations

import pytest

from ai4science.harness import registry_router as RR


# ---- fixtures: a tiny fake registry -----------------------------------------
_PRINCIPLE = {"artifact_id": "L1-003", "title": "CASSI"}
_SPEC = {"artifact_id": "L2-003", "parent_l1": "L1-003", "title": "CASSI twin",
         "spec_type": "cassi"}
_BENCH = {"artifact_id": "L3-003", "parent_l2": "L2-003", "parent_l1": "L1-003",
          "title": "CASSI benchmark", "domain": "Compressive Imaging"}
_SOLS = [
    {"label": "MST-L", "psnr_db": 35.5, "metric": "PSNR_dB", "_kind": "reference_advanced"},
    {"label": "GAP-TV", "psnr_db": 26.0, "metric": "PSNR_dB", "_kind": "reference"},
]


@pytest.fixture
def fake_registry(monkeypatch):
    monkeypatch.setattr(RR.pwm_data, "benchmark", lambda i: dict(_BENCH) if i == "L3-003" else {})
    monkeypatch.setattr(RR.pwm_data, "spec", lambda i: dict(_SPEC) if i == "L2-003" else {})
    monkeypatch.setattr(RR.pwm_data, "principle", lambda i: {"principle": dict(_PRINCIPLE)})
    monkeypatch.setattr(RR.pwm_data, "solutions", lambda i: [dict(s) for s in _SOLS] if i == "L3-003" else [])
    def _search(q, limit=20):
        ql = (q or "").lower()
        hit = "cassi" in ql or "spectral" in ql
        return {"query": q,
                "principles": [dict(_PRINCIPLE)] if hit else [],
                "specs": [dict(_SPEC)] if hit else [],
                "benchmarks": [dict(_BENCH)] if hit else []}
    monkeypatch.setattr(RR.pwm_data, "search", _search)


# ---- artifact_url -----------------------------------------------------------
def test_artifact_url_layers(monkeypatch):
    monkeypatch.setenv("PWM_SITE_BASE", "https://explorer.physicsworldmodel.org")
    assert RR.artifact_url("L1-003").endswith("/principle/L1-003")
    assert RR.artifact_url("L2-003").endswith("/spec/L2-003")
    assert RR.artifact_url("L3-003").endswith("/benchmark/L3-003")
    assert "explorer.physicsworldmodel.org" in RR.artifact_url("L3-003")


# ---- resolve_lineage --------------------------------------------------------
def test_resolve_lineage_benchmark(fake_registry):
    chain = RR.resolve_lineage("L3-003")
    assert [n["layer"] for n in chain] == ["L1", "L2", "L3"]
    assert [n["artifact_id"] for n in chain] == ["L1-003", "L2-003", "L3-003"]
    assert all(n["url"] for n in chain)


def test_resolve_lineage_spec(fake_registry):
    chain = RR.resolve_lineage("L2-003")
    assert [n["layer"] for n in chain] == ["L1", "L2"]


def test_resolve_lineage_principle(fake_registry):
    chain = RR.resolve_lineage("L1-003")
    assert [n["layer"] for n in chain] == ["L1"]


# ---- best_solution ----------------------------------------------------------
def test_best_solution_picks_max_psnr(fake_registry):
    best = RR.best_solution("L3-003")
    assert best["label"] == "MST-L"


def test_best_solution_none_when_empty(fake_registry):
    assert RR.best_solution("L3-999") is None


# ---- find_problem -----------------------------------------------------------
def test_find_problem_existing_returns_answer_and_link(fake_registry):
    out = RR.find_problem("hyperspectral cassi reconstruction")
    assert out["matched"] is True
    assert out["exists"] is True
    assert out["answer"]["label"] == "MST-L"
    assert out["url"].endswith("/benchmark/L3-003")
    assert [n["layer"] for n in out["lineage"]] == ["L1", "L2", "L3"]
    assert out["contribute"] is False


def test_find_problem_unknown_offers_contribution(fake_registry):
    out = RR.find_problem("a totally unrelated quantum gravity question")
    assert out["matched"] is False
    assert out["exists"] is False
    assert out["contribute"] is True
    assert "contribute" in out.get("contribute_hint", "").lower()


# ---- standard_check (registry-as-standard gate) -----------------------------
def test_standard_check_meets_or_beats(fake_registry):
    res = RR.standard_check("L3-003", 36.0)   # beats 35.5
    assert res["meets_or_beats"] is True
    assert res["reward_eligible"] is True
    assert res["leaderboard_best"] == 35.5


def test_standard_check_below_is_not_reward_eligible_but_reports(fake_registry):
    res = RR.standard_check("L3-003", 30.0)   # below 35.5
    assert res["meets_or_beats"] is False
    assert res["reward_eligible"] is False
    assert "below" in res["note"].lower()
    assert res["delta"] == pytest.approx(30.0 - 35.5)


def test_standard_check_no_solution_yet_sets_standard(fake_registry):
    res = RR.standard_check("L3-999", 10.0)
    assert res["meets_or_beats"] is True
    assert res["leaderboard_best"] is None
