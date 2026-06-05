from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import cassi_tools as build_cassi_tools


class _Prov:
    provider_id = "subgpu"
    endpoint_path = "/tmp/subgpu_inbox"
    wallet_address = "0xCAFE"


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def test_result_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "job_state", lambda ep, jid: {"job_id": jid, "state": "acked"})
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "acked" in out and "abc123" in out


def test_result_completed_judges(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "job_state",
                        lambda ep, jid: {"job_id": jid, "state": "completed"})
    monkeypatch.setattr(cassi_tools, "read_result",
                        lambda ep, jid: {"workspace": str(tmp_path), "benchmark_id": "L3-003"})
    monkeypatch.setattr(cassi_tools, "judge_cassi",
                        lambda submission, benchmark=None: {"final": "pass",
                                                            "score_q": 0.93, "psnr_db": 34.0})
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "0.93" in out and "34.0" in out and "pass" in out


def test_result_no_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: None)
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "[cassi error]" in out


def test_result_completed_no_result_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "job_state",
                        lambda ep, jid: {"job_id": jid, "state": "completed"})
    monkeypatch.setattr(cassi_tools, "read_result", lambda ep, jid: None)
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "[cassi error]" in out
