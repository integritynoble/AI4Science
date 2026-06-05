import numpy as np
from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import cassi_tools as build_cassi_tools
from ai4science.judge.cassi.forward import cassi_forward


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def _make_arrays(tmp_path, perturb=False):
    rng = np.random.default_rng(0)
    x = rng.random((4, 4, 3))
    mask = (rng.random((4, 4)) > 0.5).astype(float)
    y = cassi_forward(x, mask)
    if perturb:
        y = y + 1.0
    np.save(tmp_path / "recon.npy", x)
    np.save(tmp_path / "mask.npy", mask)
    np.save(tmp_path / "meas.npy", y)


def test_forward_check_consistent(tmp_path):
    _make_arrays(tmp_path, perturb=False)
    out = _tools()["cassi_forward_check"].func(
        tmp_path, recon="recon.npy", mask="mask.npy", measurement="meas.npy")
    assert "consistent" in out.lower()


def test_forward_check_inconsistent(tmp_path):
    _make_arrays(tmp_path, perturb=True)
    out = _tools()["cassi_forward_check"].func(
        tmp_path, recon="recon.npy", mask="mask.npy", measurement="meas.npy")
    assert "inconsistent" in out.lower() or "marginal" in out.lower()


def test_forward_check_path_escape(tmp_path):
    out = _tools()["cassi_forward_check"].func(
        tmp_path, recon="../x.npy", mask="mask.npy", measurement="meas.npy")
    assert "[cassi error]" in out


def test_forward_check_tool_non_mutating():
    assert _tools()["cassi_forward_check"].mutating is False
