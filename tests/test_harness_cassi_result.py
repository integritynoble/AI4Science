from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import cassi_tools as build_cassi_tools


class _Prov:
    provider_id = "subgpu"
    endpoint_path = "/tmp/subgpu_inbox"
    wallet_address = "0xCAFE"


class _FakeTx:
    token = "tok"
    def __init__(self, state, result=None):
        self._state = state
        self._result = result or {}
    def poll(self, job_id):
        return {"job_id": job_id, "state": self._state,
                "result": self._result, "reconstruction_ref": ""}
    def download_reconstruction(self, job, dest):
        return None


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def _mock(monkeypatch, tx):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr("ai4science.compute.transport.select",
                        lambda prov=None, **kw: ("http", tx))


def test_result_pending(tmp_path, monkeypatch):
    _mock(monkeypatch, _FakeTx("acked"))
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "acked" in out and "abc123" in out


def test_result_completed_judges(tmp_path, monkeypatch):
    _mock(monkeypatch, _FakeTx("completed", {"metrics": {"PSNR": 34.0}}))
    monkeypatch.setattr(cassi_tools, "judge_cassi",
                        lambda submission, benchmark=None: {"final": "pass",
                                                            "score_q": 0.93, "psnr_db": 34.0})
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "0.93" in out and "34.0" in out and "pass" in out


def test_result_no_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: None)
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "[cassi error]" in out


def test_result_completed_runs_judge_on_workspace(tmp_path, monkeypatch):
    # Completed → download reconstruction (None here) then judge the workspace.
    _mock(monkeypatch, _FakeTx("completed", {}))
    monkeypatch.setattr(cassi_tools, "judge_cassi",
                        lambda submission, benchmark=None: {"final": "needs_review"})
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "abc123" in out and "needs_review" in out
