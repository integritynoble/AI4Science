"""Universal compute-provider tools + capability wiring across modes."""
import json

import pytest

from ai4science.compute import billing
from ai4science.compute.founders import founder_providers, all_providers, THIRD_FOUNDER_WALLET
from ai4science.harness.agents import registry


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    # Empty compute registry + a private founder inbox so tests don't touch ~/.config
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "providers.json"))
    monkeypatch.setenv("AI4SCIENCE_FOUNDER_INBOX", str(tmp_path / "inbox"))
    yield


def _tool(name):
    from ai4science.harness.compute_tools import compute_tools
    return {t.name: t for t in compute_tools()}[name]


# ── founder providers ────────────────────────────────────────────────────
def test_two_founder_servers_cpu_and_gpu_x2():
    provs = {p.provider_id: p for p in founder_providers()}
    assert set(provs) == {"founder-cpu", "founder-gpu"}
    assert provs["founder-cpu"].kind == "cpu" and provs["founder-cpu"].max_concurrent == 2
    assert provs["founder-gpu"].kind == "gpu" and provs["founder-gpu"].max_concurrent == 2
    # both pay the third-founder wallet
    assert provs["founder-cpu"].wallet_address == THIRD_FOUNDER_WALLET
    assert provs["founder-gpu"].wallet_address == THIRD_FOUNDER_WALLET
    assert {p.provider_id for p in all_providers()} >= {"founder-cpu", "founder-gpu"}


# ── listing ──────────────────────────────────────────────────────────────
def test_providers_tool_lists_local_and_founders(tmp_path):
    out = _tool("compute_providers").func(tmp_path)
    assert "local" in out
    assert "founder-cpu" in out and "founder-gpu" in out
    assert THIRD_FOUNDER_WALLET in out


# ── local is free, no dispatch ───────────────────────────────────────────
def test_dispatch_local_is_free_no_job(tmp_path):
    out = _tool("compute_dispatch").func(tmp_path, provider="local", confirm=True)
    assert "local compute" in out.lower() and "no pwm" in out.lower()


# ── preview shows cost + recipient ───────────────────────────────────────
def test_dispatch_preview_shows_pwm_and_recipient(tmp_path):
    out = _tool("compute_dispatch").func(
        tmp_path, provider="founder-gpu", run_command="python train.py", max_runtime_s=3600)
    assert "preview" in out.lower()
    assert THIRD_FOUNDER_WALLET in out
    assert "est PWM" in out


# ── lease gating: 2 concurrent, 3rd refused ──────────────────────────────
def test_dispatch_is_lease_gated_at_two(tmp_path, monkeypatch):
    # pytest is non-interactive: opt in the way scripts/CI do, so the paid-
    # dispatch autonomy guard lets the lease logic under test run
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", "1")
    disp = _tool("compute_dispatch").func
    r1 = disp(tmp_path, provider="founder-cpu", run_command="a", confirm=True)
    r2 = disp(tmp_path, provider="founder-cpu", run_command="b", confirm=True)
    assert "Dispatched job" in r1 and "Dispatched job" in r2
    r3 = disp(tmp_path, provider="founder-cpu", run_command="c", confirm=True)
    assert "full" in r3.lower()


# ── billing math (1 PWM = $5 default) ────────────────────────────────────
def test_compute_pwm_math():
    # $1.50/hr for 1 hour = $1.50 = 0.30 PWM at $5/PWM
    assert billing.compute_pwm(1.50, 3600) == pytest.approx(0.30)
    assert billing.compute_pwm(0.0, 3600) == 0.0          # local/free
    # gate off by default → not charged, but returns the amount it would charge
    prov = founder_providers()[1]  # gpu @ $1.50
    charged, msg, pwm = billing.charge_compute(
        prov, seconds=3600, purpose="t", idempotency_key="k")
    assert charged is False and pwm == pytest.approx(0.30)


# ── capability wired into every user-facing mode ─────────────────────────
def test_compute_capability_in_all_modes():
    registry.reload()
    for mode in ("unified-LLM", "research", "paper", "computational-imaging"):
        spec = registry.get(mode)
        assert "compute-providers" in spec.capabilities, mode
