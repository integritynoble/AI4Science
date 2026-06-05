from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import cassi_tools as build_cassi_tools


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def _fake_get_json(mapping):
    def _g(url, timeout=60):
        for key, val in mapping.items():
            if url.endswith(key):
                return val
        raise RuntimeError(f"unmocked url {url}")
    return _g


_BENCHMARKS = {"genesis": [{"benchmark_id": "L3-003", "title": "CASSI Mismatch Suite",
                            "category": "computational-imaging"},
                           {"benchmark_id": "L9-001", "title": "Unrelated", "category": "x"}]}
_LEADERBOARD = {"benchmark_id": "L3-003",
                "reference_advanced": {"label": "MST-L", "score_q": 0.95, "psnr_db": 35.3}}


def test_solutions_testnet_only_marks_chain(tmp_path, monkeypatch):
    monkeypatch.delenv("PWM_EXPLORER_BASE_MAINNET", raising=False)
    monkeypatch.setattr(cassi_tools.transport, "get_json",
                        _fake_get_json({"/benchmarks": _BENCHMARKS,
                                        "/leaderboard/L3-003": _LEADERBOARD}))
    out = _tools()["cassi_solutions"].func(tmp_path, benchmark="")
    assert "[testnet]" in out and "MST-L" in out and "L3-003" in out
    assert "[mainnet]" not in out
    assert "mainnet: not configured" in out


def test_solutions_both_chains(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_EXPLORER_BASE_MAINNET", "https://mainnet.example/api")
    monkeypatch.setattr(cassi_tools.transport, "get_json",
                        _fake_get_json({"/benchmarks": _BENCHMARKS,
                                        "/leaderboard/L3-003": _LEADERBOARD}))
    out = _tools()["cassi_solutions"].func(tmp_path, benchmark="L3-003")
    assert "[mainnet]" in out and "[testnet]" in out


def test_solutions_one_chain_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_EXPLORER_BASE_MAINNET", "https://mainnet.example/api")
    def _g(url, timeout=60):
        if url.startswith("https://mainnet.example"):
            raise RuntimeError("down")
        if url.endswith("/leaderboard/L3-003"):
            return _LEADERBOARD
        raise RuntimeError("unmocked")
    monkeypatch.setattr(cassi_tools.transport, "get_json", _g)
    out = _tools()["cassi_solutions"].func(tmp_path, benchmark="L3-003")
    assert "[testnet]" in out and "unavailable" in out.lower()
