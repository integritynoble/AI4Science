"""Autonomy guard: paid compute dispatch needs HUMAN confirmation (2026-06-10)."""
import sys
import types

import pytest

from ai4science.harness import compute_tools


class _Prov:
    provider_id = "founder-1-subgpu"
    def pwm_per_hour(self):
        return 0.30


def test_non_interactive_blocks(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", raising=False)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: False))
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is False and "blocked" in why and "AUTOCONFIRM" in why


def test_env_optin_allows(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", "1")
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is True and why == ""


def test_tty_decline(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", raising=False)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _p: "n")
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is False and "declined" in why


def test_tty_accept(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", raising=False)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _p: "y")
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is True


def test_tty_eof_cancels(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", raising=False)
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    def _raise(_p):
        raise EOFError
    monkeypatch.setattr("builtins.input", _raise)
    ok, why = compute_tools._confirm_paid_dispatch(_Prov(), 0.3, 3600)
    assert ok is False and "cancelled" in why
