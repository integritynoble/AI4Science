"""Compute dispatch: auto-use the GPU for normal jobs; confirm/guard big ones."""
import sys
import types

import pytest

from ai4science.harness import compute_tools


class _Prov:
    provider_id = "founder-1-subgpu"
    kind = "gpu"
    def pwm_per_hour(self):
        return 0.30


def _no_auto(monkeypatch):
    """Disable auto-approve so the human-confirm path is exercised."""
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", raising=False)
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTO", "0")


def test_auto_small_job_allows(monkeypatch):
    # default: a normal-cost job auto-dispatches, no prompt
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", raising=False)
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTO", raising=False)
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is True and why == ""


def test_auto_large_job_blocks_noninteractive(monkeypatch):
    # cost above the auto-approve ceiling falls back to confirm → blocked in CI
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", raising=False)
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTO", raising=False)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: False))
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 5.0, 60000)
    assert ok is False and "blocked" in why


def test_env_optin_allows(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", "1")
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 9.9, 3600)
    assert ok is True and why == ""


def test_auto_off_non_interactive_blocks(monkeypatch):
    _no_auto(monkeypatch)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: False))
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is False and "blocked" in why


def test_tty_decline(monkeypatch):
    _no_auto(monkeypatch)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _p: "n")
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is False and "declined" in why


def test_tty_accept(monkeypatch):
    _no_auto(monkeypatch)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _p: "y")
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is True


def test_tty_eof_cancels(monkeypatch):
    _no_auto(monkeypatch)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    def _raise(_p):
        raise EOFError
    monkeypatch.setattr("builtins.input", _raise)
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is False and "cancelled" in why
