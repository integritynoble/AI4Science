from __future__ import annotations

from ai4science.harness import pwm_data, transport


def test_principles(monkeypatch):
    monkeypatch.setattr(transport, "get_json",
                        lambda url, timeout=60: {"genesis": [{"artifact_id": "L1-003", "title": "CASSI"}]})
    out = pwm_data.principles()
    assert out[0]["artifact_id"] == "L1-003"


def test_solutions_for_benchmark(monkeypatch):
    monkeypatch.setattr(transport, "get_json",
                        lambda url, timeout=60: {"benchmark_id": "L3-003",
                                                 "reference": {"label": "GAP-TV", "score_q": 0.62},
                                                 "reference_advanced": {"label": "MST-L", "score_q": 0.95}})
    sols = pwm_data.solutions("L3-003")
    labels = {s["label"] for s in sols}
    assert "GAP-TV" in labels and "MST-L" in labels


def test_base_url_env(monkeypatch):
    monkeypatch.setenv("PWM_EXPLORER_BASE", "http://local/api")
    assert pwm_data.base() == "http://local/api"
