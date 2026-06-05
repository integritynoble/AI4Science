from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import (
    cassi_tools as build_cassi_tools, _solution_cost, GENESIS_SOLUTION_PROVIDER)


class _Prov:
    provider_id = "subgpu"
    endpoint_path = "/tmp/subgpu_inbox"
    wallet_address = "0xCAFE"


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def test_solution_cost_own_vs_registered():
    cost, recipient, prov = _solution_cost("")
    assert recipient == "you"
    cost, recipient, prov = _solution_cost("L3-003-sol-1")
    assert recipient == GENESIS_SOLUTION_PROVIDER and "L3-003-sol-1" in prov


def test_dispatch_preview_no_spend(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "dispatch_job",
                        lambda **k: (_ for _ in ()).throw(AssertionError("should not dispatch")))
    out = _tools()["cassi_dispatch"].func(
        tmp_path, benchmark="L3-003-T1", solver="code/", solution_ref="L3-003-sol-1")
    assert "preview" in out.lower()
    assert GENESIS_SOLUTION_PROVIDER in out
    assert "subgpu" in out


def test_dispatch_confirm_dispatches(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    class _Job: job_id = "abc123"
    monkeypatch.setattr(cassi_tools, "dispatch_job", lambda **k: _Job())
    out = _tools()["cassi_dispatch"].func(
        tmp_path, benchmark="L3-003-T1", solver="code/", confirm=True)
    assert "abc123" in out and "cassi_result" in out


def test_dispatch_no_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: None)
    out = _tools()["cassi_dispatch"].func(tmp_path, benchmark="L3-003-T1")
    assert "[cassi error]" in out and "provider" in out.lower()


def test_dispatch_non_mutating():
    assert _tools()["cassi_dispatch"].mutating is False


def test_dispatch_string_false_does_not_spend(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "dispatch_job",
                        lambda **k: (_ for _ in ()).throw(AssertionError("must not dispatch")))
    # An LLM passing the STRING "false" must NOT trigger a real dispatch.
    out = _tools()["cassi_dispatch"].func(
        tmp_path, benchmark="L3-003-T1", solver="code/", confirm="false")
    assert "preview" in out.lower()


def test_dispatch_string_true_does_not_spend(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "dispatch_job",
                        lambda **k: (_ for _ in ()).throw(AssertionError("must not dispatch")))
    # Only a real boolean True confirms; the string "true" stays in preview (safe default).
    out = _tools()["cassi_dispatch"].func(
        tmp_path, benchmark="L3-003-T1", solver="code/", confirm="true")
    assert "preview" in out.lower()
