"""Tests for the CASSI judge."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from ai4science.cli import app
from ai4science.judge.cassi import judge_cassi

runner = CliRunner()


def _init_cassi(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init", "demo"])
    assert r.exit_code == 0, r.output
    return tmp_path / "demo"


def test_judge_creates_report_and_marks_s4_not_available(tmp_path: Path, monkeypatch):
    """With no data/ or results/ files, S4 sub-checks return not_available."""
    ws = _init_cassi(tmp_path, monkeypatch)
    report = judge_cassi(ws)
    assert (ws / "reports" / "judge_report.json").exists()

    persisted = json.loads((ws / "reports" / "judge_report.json").read_text())
    assert persisted["s1_status"] == "pass"
    assert persisted["s3_status"] == "pass"
    # All S4 sub-checks should be not_available when no data files exist.
    for sub in persisted["s4_checks"].values():
        assert sub["status"] == "not_available"
    assert persisted["s4_status"] == "not_available"
    assert persisted["final_decision"] == "needs_review"
    assert persisted["silent_failure"] is False
    assert report == persisted


def test_judge_passes_with_consistent_synthetic_data(tmp_path: Path, monkeypatch):
    """Synthesize y, x_hat that satisfy y == sum(x_hat, axis=-1) + tiny noise."""
    ws = _init_cassi(tmp_path, monkeypatch)
    rng = np.random.default_rng(0)
    # 32x32 spatial with 4 spectral channels — small + 2-D-friendly for the FFT check.
    # Use noise sigma matching the example spec's declared noise_sigma=0.01.
    x = rng.uniform(0.1, 0.9, size=(32, 32, 4)).astype(np.float32)
    y = x.sum(axis=-1) + rng.normal(0.0, 0.01, size=(32, 32)).astype(np.float32)

    (ws / "data").mkdir(exist_ok=True)
    (ws / "results").mkdir(exist_ok=True)
    np.save(ws / "data" / "measurement_y.npy", y)
    np.save(ws / "results" / "reconstruction_xhat.npy", x)

    report = judge_cassi(ws)
    assert report["s1_status"] == "pass"
    assert report["s3_status"] == "pass"
    # At least the forward-residual check should pass.
    assert report["s4_checks"]["forward_residual"]["status"] == "pass"
    assert report["final_decision"] in ("pass", "needs_review")
    # Critically, no silent failure on clean synthetic data.
    assert report["silent_failure"] is False


def test_judge_flags_silent_failure_on_corrupted_recon(tmp_path: Path, monkeypatch):
    """Garbage reconstruction (zeros) + non-zero measurement → S4 should fail."""
    ws = _init_cassi(tmp_path, monkeypatch)
    rng = np.random.default_rng(1)
    y = rng.uniform(0.5, 1.5, size=(32, 32)).astype(np.float32)
    x = np.zeros((32, 32, 4), dtype=np.float32)  # totally wrong reconstruction

    (ws / "data").mkdir(exist_ok=True)
    (ws / "results").mkdir(exist_ok=True)
    np.save(ws / "data" / "measurement_y.npy", y)
    np.save(ws / "results" / "reconstruction_xhat.npy", x)

    report = judge_cassi(ws)
    assert report["s1_status"] == "pass"
    assert report["s3_status"] == "pass"
    # Forward residual should fail (or warn) on garbage recon.
    assert report["s4_checks"]["forward_residual"]["status"] in ("fail", "warning")
    # If forward_residual failed, this is a silent failure pattern.
    if report["s4_checks"]["forward_residual"]["status"] == "fail":
        assert report["silent_failure"] is True
        assert report["final_decision"] == "fail"
