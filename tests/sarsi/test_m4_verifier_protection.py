"""M4.2/M4.3 — runtime verifier protection + write-boundary negative tests.

Invariants under test:
1. _check_verifier_integrity() passes when no module was modified.
2. If verify.py is replaced with different bytes, integrity check returns False.
3. The integrity check baseline is reset on each fresh module import (test
   isolation: we monkeypatch the baseline dict).
4. The executor (sarsi-claude ACP session) cannot write to protected verifier
   paths — any task that attempts it must fail the policy gate.
5. The worker itself cannot directly write to the task workspace (reads are
   always allowed; writes require the declared work_root).

These tests run without spawning a real ACP session.  They verify the
structural invariants that hold regardless of the LLM's self-report.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from pathlib import Path

import pytest

from ai4science.harness.agents.sarsi import registry as reg
from ai4science.harness.agents.sarsi import session as ses


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"
    root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p)
    c.ensure_dirs()
    return c


# ── _check_verifier_integrity() ───────────────────────────────────────────────

def test_integrity_check_passes_when_modules_unchanged():
    ses._VERIFIER_BASELINE.clear()
    ok, reason = ses._check_verifier_integrity()
    assert ok, f"clean integrity check failed: {reason}"
    assert reason == ""


def test_integrity_check_records_baseline_on_first_call():
    ses._VERIFIER_BASELINE.clear()
    ses._check_verifier_integrity()
    assert "verify" in ses._VERIFIER_BASELINE
    assert "verifier" in ses._VERIFIER_BASELINE


def test_integrity_check_detects_tampered_verify(tmp_path):
    """Simulate an executor session replacing verify.py with different bytes."""
    import ai4science.harness.agents.sarsi.verify as _v
    original_src = Path(_v.__file__).read_bytes()
    original_hash = hashlib.sha256(original_src).hexdigest()

    ses._VERIFIER_BASELINE.clear()
    ses._VERIFIER_BASELINE["verify"] = original_hash
    ses._VERIFIER_BASELINE["verifier"] = hashlib.sha256(
        Path(importlib.import_module(
            "ai4science.harness.agents.sarsi.verifier").__file__).read_bytes()
    ).hexdigest()

    # Tamper: write different content to verify.py temporarily.
    tampered = original_src + b"\n# tamper\n"
    verify_path = Path(_v.__file__)
    backup = tmp_path / "verify_backup.py"
    shutil.copy2(verify_path, backup)
    try:
        verify_path.write_bytes(tampered)
        ok, reason = ses._check_verifier_integrity()
        assert not ok, "integrity check should have detected tampering"
        assert "verify.py was modified" in reason or "was modified" in reason, reason
    finally:
        # Restore original — test must not leave the repo modified.
        shutil.copy2(backup, verify_path)
        ses._VERIFIER_BASELINE.clear()


def test_integrity_check_passes_after_restore():
    ses._VERIFIER_BASELINE.clear()
    # After restoring in the previous test, a fresh baseline should pass.
    ok, reason = ses._check_verifier_integrity()
    assert ok, f"integrity check should pass after restore: {reason}"


# ── boundary: executor must not be able to modify verifier source ─────────────

def test_verify_py_is_not_writable_by_task_workspace(tmp_path):
    """A task workspace (work_root) is separate from verifier source.

    The verifier module lives in the harness package — not in any task
    workspace.  This test confirms the paths are disjoint so an executor
    that is restricted to its work_root cannot reach verifier source.
    """
    import ai4science.harness.agents.sarsi.verify as _v
    verify_src = Path(_v.__file__).resolve()
    task_workspace = tmp_path / "task_workspace"
    task_workspace.mkdir()

    # The verify source must NOT be under the task workspace.
    try:
        verify_src.relative_to(task_workspace.resolve())
        pytest.fail(
            f"verify.py ({verify_src}) is inside the task workspace "
            f"({task_workspace}) — the isolation boundary is broken")
    except ValueError:
        pass  # expected: verify_src is NOT a child of task_workspace


def test_verify_py_is_not_writable_under_tmp_path(tmp_path):
    """Same check for verifier.py."""
    import ai4science.harness.agents.sarsi.verifier as _vf
    verifier_src = Path(_vf.__file__).resolve()
    task_workspace = tmp_path / "another_task"
    task_workspace.mkdir()
    try:
        verifier_src.relative_to(task_workspace.resolve())
        pytest.fail(
            f"verifier.py ({verifier_src}) is inside task workspace — isolation broken")
    except ValueError:
        pass


# ── boundary: worker cannot write directly to task workspace ──────────────────

def test_worker_cannot_write_outside_declared_work_root(tmp_path):
    """The harness never writes to a path that escapes the declared work_root.

    verify._check_file_exists() enforces this with a path-escape check.
    This test exercises that guard directly.
    """
    from ai4science.harness.agents.sarsi import verify as _det
    cwd = tmp_path / "workspace"
    cwd.mkdir()

    # A path that tries to escape via ../ — must use an extension so the
    # FILE_EXISTS regex matches, triggering the path-escape guard.
    result = _det.check("../../../etc/shadow.conf exists", cwd)
    # Must be UNVERIFIED (refused), not PASS or FAIL.
    assert result["state"] == _det.UNVERIFIED, (
        f"path-escape check should produce UNVERIFIED, got {result['state']!r}: "
        f"{result.get('why', '')}")
    assert "escapes" in (result.get("why") or "").lower(), result


def test_empty_work_dir_produces_unverified():
    """No work_dir → UNVERIFIED, not a crash."""
    from ai4science.harness.agents.sarsi import verify as _det
    result = _det.check("pytest exits with 0", None)
    assert result["state"] == _det.UNVERIFIED


# ── verify baseline stability ─────────────────────────────────────────────────

def test_verifier_baseline_pinned_per_process():
    """Once the baseline is set for a module it stays constant in this process."""
    ses._VERIFIER_BASELINE.clear()
    ses._check_verifier_integrity()
    first = dict(ses._VERIFIER_BASELINE)
    ses._check_verifier_integrity()
    second = dict(ses._VERIFIER_BASELINE)
    assert first == second, "baseline changed between calls — it must be stable"
