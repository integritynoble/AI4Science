"""Tests for the provider-side poller (sub-GPU)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

PY = sys.executable   # the venv python — bare "python" may not be on PATH

from ai4science.compute.dispatch import dispatch_job
from ai4science.compute.registry import ComputeProvider
from ai4science.compute.provider import (
    pending_jobs, process_job, poll_once, run_solver,
    compute_certificate_hash, build_result_manifest,
)

DIRECTOR_WALLET = "0xf1Fa5803daAAaFf89932592ad54F4e7F5e3f7DEE"


def _provider(tmp_path) -> ComputeProvider:
    return ComputeProvider(provider_id="founder-1-subgpu",
                           wallet_address=DIRECTOR_WALLET,
                           endpoint_path=str(tmp_path / "jobs"),
                           gpu_capability={"device": "CUDA 12.7"})


# ─── pending_jobs ────────────────────────────────────────────────────


def test_pending_jobs_finds_requests(tmp_path):
    prov = _provider(tmp_path)
    dispatch_job(provider=prov, workspace=tmp_path)
    dispatch_job(provider=prov, workspace=tmp_path)
    assert len(pending_jobs(Path(prov.endpoint_path))) == 2


def test_pending_jobs_skips_acked_and_completed(tmp_path):
    prov = _provider(tmp_path)
    job = dispatch_job(provider=prov, workspace=tmp_path)
    inbox = Path(prov.endpoint_path)
    (inbox / f"job_{job.job_id}.ack.json").write_text("{}")
    assert pending_jobs(inbox) == []   # acked → in flight, not pending


def test_pending_jobs_empty_dir(tmp_path):
    assert pending_jobs(tmp_path / "nope") == []


# ─── run_solver ──────────────────────────────────────────────────────


def test_run_solver_success(tmp_path):
    out = run_solver(tmp_path, f'{PY} -c "print(\'hi\')"', timeout_s=30)
    assert out["ok"] is True
    assert out["returncode"] == 0
    assert "hi" in out["stdout_tail"]


def test_run_solver_nonzero(tmp_path):
    out = run_solver(tmp_path, f'{PY} -c "import sys; sys.exit(3)"', timeout_s=30)
    assert out["ok"] is False
    assert out["returncode"] == 3


def test_run_solver_bad_command(tmp_path):
    out = run_solver(tmp_path, "this_binary_does_not_exist_xyz", timeout_s=30)
    assert out["ok"] is False
    assert "error" in out


# ─── certificate hash ────────────────────────────────────────────────


def test_certificate_hash_deterministic(tmp_path):
    (tmp_path / "results").mkdir()
    np.save(tmp_path / "results" / "reconstruction_xhat.npy", np.ones((4, 4, 2)))
    job = {"job_id": "j", "benchmark_id": "T1", "wallet_address": DIRECTOR_WALLET}
    h1 = compute_certificate_hash(tmp_path, job, {"PSNR": 30})
    h2 = compute_certificate_hash(tmp_path, job, {"PSNR": 30})
    assert h1 == h2
    assert h1.startswith("0x")


def test_certificate_hash_changes_with_content(tmp_path):
    (tmp_path / "results").mkdir()
    recon = tmp_path / "results" / "reconstruction_xhat.npy"
    job = {"job_id": "j", "benchmark_id": "T1", "wallet_address": DIRECTOR_WALLET}
    np.save(recon, np.ones((4, 4, 2)))
    h1 = compute_certificate_hash(tmp_path, job, {})
    np.save(recon, np.zeros((4, 4, 2)))
    h2 = compute_certificate_hash(tmp_path, job, {})
    assert h1 != h2   # different reconstruction → different certificate


# ─── process_job end-to-end (with a trivial solver) ──────────────────


def test_process_job_runs_solver_and_writes_result(tmp_path):
    prov = _provider(tmp_path)
    ws = tmp_path / "ws"
    (ws / "results").mkdir(parents=True)
    # A trivial "solver": writes a reconstruction + a results.json.
    solver = ws / "solve.py"
    solver.write_text(
        "import numpy as np, json, pathlib\n"
        "np.save('results/reconstruction_xhat.npy', np.ones((4,4,2)))\n"
        "pathlib.Path('results/results.json').write_text(json.dumps({'PSNR': 31.0}))\n"
    )
    job = dispatch_job(provider=prov, workspace=ws,
                       run_command=f"{PY} solve.py")
    req = Path(prov.endpoint_path) / f"job_{job.job_id}.request.json"

    manifest = process_job(req, prov.model_dump(), allow_exec=True)

    assert manifest["solver_ran"] is True
    assert manifest["metrics"] == {"PSNR": 31.0}
    assert manifest["reconstruction_artifacts"] == ["results/reconstruction_xhat.npy"]
    assert manifest["provider"]["wallet_address"] == DIRECTOR_WALLET
    assert manifest["certificate_hash"].startswith("0x")
    # ack + result files now exist
    inbox = Path(prov.endpoint_path)
    assert (inbox / f"job_{job.job_id}.ack.json").exists()
    assert (inbox / f"job_{job.job_id}.result.json").exists()
    # reconstruction actually produced
    assert (ws / "results" / "reconstruction_xhat.npy").exists()


def test_process_job_refuses_without_allow_exec(tmp_path):
    prov = _provider(tmp_path)
    ws = tmp_path / "ws"; ws.mkdir()
    job = dispatch_job(provider=prov, workspace=ws,
                       run_command=f'{PY} -c "open(\'x\',\'w\')"')
    req = Path(prov.endpoint_path) / f"job_{job.job_id}.request.json"

    manifest = process_job(req, prov.model_dump(), allow_exec=False)
    assert manifest["solver_ran"] is False
    assert "execution disabled" in (manifest["solver_error"] or "")
    # the side-effect file must NOT exist — code did not run
    assert not (ws / "x").exists()


def test_process_job_handles_missing_workspace(tmp_path):
    prov = _provider(tmp_path)
    job = dispatch_job(provider=prov, workspace=tmp_path / "ghost")
    # remove nothing — ghost workspace never existed
    req = Path(prov.endpoint_path) / f"job_{job.job_id}.request.json"
    manifest = process_job(req, prov.model_dump(), allow_exec=True)
    assert manifest["solver_ran"] is False
    assert "not reachable" in (manifest["solver_error"] or "")


def test_poll_once_processes_then_idempotent(tmp_path):
    prov = _provider(tmp_path)
    ws = tmp_path / "ws"; (ws / "results").mkdir(parents=True)
    (ws / "solve.py").write_text(
        "import numpy as np; np.save('results/reconstruction_xhat.npy', np.ones((4,4,2)))")
    dispatch_job(provider=prov, workspace=ws, run_command=f"{PY} solve.py")

    first = poll_once(prov.model_dump(), allow_exec=True)
    assert len(first) == 1
    # Second pass: the job now has a result → not pending → nothing processed.
    second = poll_once(prov.model_dump(), allow_exec=True)
    assert second == []
