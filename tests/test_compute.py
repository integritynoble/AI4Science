"""Tests for the compute layer: registry, dispatch, attribution."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from ai4science.cli import app
from ai4science.compute import (
    ComputeProvider, is_valid_eth_address, add_provider, load_registry,
)
from ai4science.compute.registry import get_provider
from ai4science.compute.dispatch import dispatch_job, job_state, new_job_id
from ai4science.compute.attribution import (
    verify_and_attribute, credit_summary, read_attributions,
)

runner = CliRunner()

DIRECTOR_WALLET = "0xf1Fa5803daAAaFf89932592ad54F4e7F5e3f7DEE"


# ─── Address validation ──────────────────────────────────────────────


def test_valid_director_address():
    assert is_valid_eth_address(DIRECTOR_WALLET) is True


def test_invalid_addresses_rejected():
    assert not is_valid_eth_address("0x123")             # too short
    assert not is_valid_eth_address("f1Fa5803" * 5)      # no 0x
    assert not is_valid_eth_address("0x" + "z" * 40)     # non-hex
    assert not is_valid_eth_address("")
    assert not is_valid_eth_address(None)  # type: ignore


def test_provider_rejects_bad_address():
    with pytest.raises(ValueError, match="invalid Ethereum address"):
        ComputeProvider(provider_id="x", wallet_address="nope",
                        endpoint_path="/tmp/x")


def test_provider_preserves_checksum_casing():
    p = ComputeProvider(provider_id="prov", wallet_address=DIRECTOR_WALLET,
                        endpoint_path="/tmp/x")
    assert p.wallet_address == DIRECTOR_WALLET   # exact casing preserved


# ─── Registry roundtrip ──────────────────────────────────────────────


def test_registry_add_load_get(tmp_path):
    reg = tmp_path / "providers.json"
    p = ComputeProvider(provider_id="founder-1-subgpu",
                        wallet_address=DIRECTOR_WALLET,
                        endpoint_path=str(tmp_path / "jobs"),
                        trust_tier="founder")
    add_provider(p, path=reg)
    loaded = load_registry(reg)
    assert len(loaded) == 1
    assert loaded[0].provider_id == "founder-1-subgpu"
    assert loaded[0].wallet_address == DIRECTOR_WALLET
    assert get_provider("founder-1-subgpu", reg).trust_tier == "founder"


def test_registry_replace_by_id(tmp_path):
    reg = tmp_path / "providers.json"
    add_provider(ComputeProvider(provider_id="prov", wallet_address=DIRECTOR_WALLET,
                                 endpoint_path="/tmp/a"), path=reg)
    add_provider(ComputeProvider(provider_id="prov", wallet_address=DIRECTOR_WALLET,
                                 endpoint_path="/tmp/b", status="disabled"), path=reg)
    loaded = load_registry(reg)
    assert len(loaded) == 1            # replaced, not duplicated
    assert loaded[0].endpoint_path == "/tmp/b"
    assert loaded[0].status == "disabled"


# ─── Dispatch handshake ──────────────────────────────────────────────


def _provider(tmp_path) -> ComputeProvider:
    return ComputeProvider(provider_id="founder-1-subgpu",
                           wallet_address=DIRECTOR_WALLET,
                           endpoint_path=str(tmp_path / "jobs"))


def test_dispatch_writes_request(tmp_path):
    prov = _provider(tmp_path)
    job = dispatch_job(provider=prov, workspace=tmp_path, benchmark_id="L3-003-001-001-T1")
    req = Path(prov.endpoint_path) / f"job_{job.job_id}.request.json"
    assert req.exists()
    data = json.loads(req.read_text())
    assert data["wallet_address"] == DIRECTOR_WALLET
    assert data["benchmark_id"] == "L3-003-001-001-T1"


def test_job_state_transitions(tmp_path):
    prov = _provider(tmp_path)
    job = dispatch_job(provider=prov, workspace=tmp_path)
    endpoint = Path(prov.endpoint_path)

    assert job_state(endpoint, job.job_id)["state"] == "requested"

    (endpoint / f"job_{job.job_id}.ack.json").write_text('{"accepted": true}')
    assert job_state(endpoint, job.job_id)["state"] == "acked"

    (endpoint / f"job_{job.job_id}.result.json").write_text(
        '{"certificate_hash": "0xabc", "metrics": {"PSNR": 30}}')
    st = job_state(endpoint, job.job_id)
    assert st["state"] == "completed"
    assert st["result"]["certificate_hash"] == "0xabc"


def test_job_state_missing(tmp_path):
    assert job_state(tmp_path / "jobs", "nope")["state"] == "missing"


# ─── Attribution (judge re-verification) ─────────────────────────────


def _init_demo(tmp_path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init", "demo"])
    assert r.exit_code == 0, r.output
    return tmp_path / "demo"


def _make_cassi_arrays(ws: Path, good: bool):
    """Create measurement + reconstruction. good=True → near-perfect recon
    (passes S4); good=False → zeros (silent failure)."""
    from ai4science.judge.cassi.forward import cassi_forward
    rng = np.random.default_rng(0)
    H, W, C = 16, 16, 4
    x = rng.uniform(0.1, 0.9, size=(H, W, C))
    mask = (rng.random((H, W)) > 0.5).astype(float)
    y = cassi_forward(x, mask) + rng.normal(0, 0.01, size=(H, W + C - 1))
    (ws / "data").mkdir(exist_ok=True)
    (ws / "results").mkdir(exist_ok=True)
    np.save(ws / "data" / "measurement_y.npy", y)
    np.save(ws / "data" / "coded_aperture_phi.npy", mask)
    np.save(ws / "results" / "reconstruction_xhat.npy",
            x if good else np.zeros_like(x))


def test_attribution_awards_credit_on_pass(tmp_path, monkeypatch):
    ws = _init_demo(tmp_path, monkeypatch)
    _make_cassi_arrays(ws, good=True)
    job = {"job_id": "j1", "provider_id": "founder-1-subgpu",
           "wallet_address": DIRECTOR_WALLET, "benchmark_id": "T1"}
    attr = verify_and_attribute(workspace=ws, job=job,
                                result_manifest={"certificate_hash": "0xabc"})
    assert attr["judge_decision"] == "pass"
    assert attr["credit"] == 1
    assert attr["wallet_address"] == DIRECTOR_WALLET


def test_attribution_no_credit_on_silent_failure(tmp_path, monkeypatch):
    ws = _init_demo(tmp_path, monkeypatch)
    _make_cassi_arrays(ws, good=False)   # zeros → S4 fails
    job = {"job_id": "j2", "provider_id": "founder-1-subgpu",
           "wallet_address": DIRECTOR_WALLET}
    attr = verify_and_attribute(workspace=ws, job=job)
    assert attr["credit"] == 0
    assert attr["judge_decision"] in ("fail", "needs_review")


def test_credit_summary_aggregates_by_wallet(tmp_path, monkeypatch):
    ws = _init_demo(tmp_path, monkeypatch)
    _make_cassi_arrays(ws, good=True)
    job = {"job_id": "j", "provider_id": "p", "wallet_address": DIRECTOR_WALLET}
    verify_and_attribute(workspace=ws, job=job)
    verify_and_attribute(workspace=ws, job=job)
    totals = credit_summary(ws)
    assert totals[DIRECTOR_WALLET] == 2
    assert len(read_attributions(ws)) == 2


# ─── CLI surface ─────────────────────────────────────────────────────


def test_cli_providers_add_rejects_bad_wallet(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "reg.json"))
    r = runner.invoke(app, ["compute", "providers-add", "--id", "x",
                            "--wallet", "not-an-address", "--endpoint", "/tmp/j"])
    assert r.exit_code == 2
    assert "invalid wallet" in r.output.lower()


def test_cli_providers_add_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "reg.json"))
    r = runner.invoke(app, ["compute", "providers-add",
                            "--id", "founder-1-subgpu",
                            "--wallet", DIRECTOR_WALLET,
                            "--endpoint", str(tmp_path / "jobs"),
                            "--tier", "founder"])
    assert r.exit_code == 0, r.output
    assert "founder-1-subgpu" in r.output
    r2 = runner.invoke(app, ["compute", "providers"])
    assert "founder-1-subgpu" in r2.output
    assert DIRECTOR_WALLET[:10] in r2.output
