"""Provider-side solver helpers (the git inbox poller was removed in P4).

These helpers are now exercised over HTTP by http_provider (see
test_http_transport.py for the end-to-end round-trip); here we unit-test them
directly: run_solver, compute_certificate_hash, build_result_manifest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PY = sys.executable   # the venv python — bare "python" may not be on PATH

from ai4science.compute.provider import (
    run_solver, compute_certificate_hash, build_result_manifest,
)

DIRECTOR_WALLET = "0xf1Fa5803daAAaFf89932592ad54F4e7F5e3f7DEE"


# ─── run_solver ──────────────────────────────────────────────────────
def test_run_solver_success(tmp_path):
    out = run_solver(tmp_path, f'{PY} -c "print(\'hi\')"', timeout_s=30)
    assert out["ok"] is True and out["returncode"] == 0
    assert "hi" in out["stdout_tail"]


def test_run_solver_nonzero(tmp_path):
    out = run_solver(tmp_path, f'{PY} -c "import sys; sys.exit(3)"', timeout_s=30)
    assert out["ok"] is False and out["returncode"] == 3


def test_run_solver_bad_command(tmp_path):
    out = run_solver(tmp_path, "this_binary_does_not_exist_xyz", timeout_s=30)
    assert out["ok"] is False and "error" in out


# ─── certificate hash ────────────────────────────────────────────────
def test_certificate_hash_deterministic(tmp_path):
    (tmp_path / "results").mkdir()
    np.save(tmp_path / "results" / "reconstruction_xhat.npy", np.ones((4, 4, 2)))
    job = {"job_id": "j", "benchmark_id": "T1", "wallet_address": DIRECTOR_WALLET}
    h1 = compute_certificate_hash(tmp_path, job, {"PSNR": 30})
    h2 = compute_certificate_hash(tmp_path, job, {"PSNR": 30})
    assert h1 == h2 and h1.startswith("0x")


def test_certificate_hash_changes_with_content(tmp_path):
    (tmp_path / "results").mkdir()
    recon = tmp_path / "results" / "reconstruction_xhat.npy"
    job = {"job_id": "j", "benchmark_id": "T1", "wallet_address": DIRECTOR_WALLET}
    np.save(recon, np.ones((4, 4, 2)))
    h1 = compute_certificate_hash(tmp_path, job, {})
    np.save(recon, np.zeros((4, 4, 2)))
    h2 = compute_certificate_hash(tmp_path, job, {})
    assert h1 != h2


# ─── build_result_manifest (what the provider returns) ───────────────
def test_build_result_manifest_shape(tmp_path):
    (tmp_path / "results").mkdir()
    np.save(tmp_path / "results" / "reconstruction_xhat.npy", np.ones((4, 4, 2)))
    job = {"job_id": "abc", "benchmark_id": "T1", "run_command": "python x.py"}
    prov = {"provider_id": "founder-1-subgpu", "wallet_address": DIRECTOR_WALLET}
    outcome = {"ok": True, "returncode": 0, "stdout_tail": "done", "stderr_tail": ""}
    m = build_result_manifest(job, tmp_path, prov, outcome, wall_clock_s=1.5)
    assert m["job_id"] == "abc" and m["solver_ran"] is True
    assert m["solver_returncode"] == 0
    assert m["certificate_hash"].startswith("0x")
    assert m["provider"]["wall_clock_s"] == 1.5
