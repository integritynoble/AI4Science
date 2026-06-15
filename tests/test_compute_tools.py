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
    # one job at a time on each founder box (single CPU slot / single GPU)
    assert provs["founder-cpu"].kind == "cpu" and provs["founder-cpu"].max_concurrent == 1
    assert provs["founder-gpu"].kind == "gpu" and provs["founder-gpu"].max_concurrent == 1
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


# ── dispatch over the HTTP relay (P4: git transport removed) ──────────────
def test_dispatch_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", "1")
    monkeypatch.delenv("PWM_TOKEN", raising=False)
    import ai4science.compute.transport as tmod
    # no token → HttpTransport has empty token → tool tells the user to log in
    monkeypatch.setattr("ai4science.pwm_account.load", lambda: {}, raising=False)
    out = _tool("compute_dispatch").func(tmp_path, provider="founder-gpu",
                                         run_command="a", confirm=True)
    assert "not logged in" in out.lower()


def test_dispatch_over_http_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", "1")
    import ai4science.harness.compute_tools as ct

    class _FakeTx:
        token = "tok"
        def dispatch(self, *, provider_id, run_command, workspace, max_runtime_s):
            return {"job_id": "job-xyz", "state": "requested"}
    monkeypatch.setattr("ai4science.compute.transport.select",
                        lambda prov: ("http", _FakeTx()))
    out = ct._dispatch_tool().func(tmp_path, provider="founder-gpu",
                                   run_command="a", confirm=True)
    assert "Dispatched job job-xyz" in out and "founder-gpu" in out


# ── billing math (native PWM/hr) ─────────────────────────────────────────
def test_compute_pwm_math():
    # 0.30 PWM/hr for 1 hour = 0.30 PWM
    assert billing.compute_pwm(0.30, 3600) == pytest.approx(0.30)
    assert billing.compute_pwm(0.0, 3600) == 0.0          # local/free
    # gate off by default → not charged, but returns the amount it would charge
    prov = founder_providers()[1]  # gpu @ 0.30 PWM/hr
    charged, msg, pwm = billing.charge_compute(
        prov, seconds=3600, purpose="t", idempotency_key="k")
    assert charged is False and pwm == pytest.approx(0.30)


# ── capability wired into every user-facing mode ─────────────────────────
def test_compute_capability_in_all_modes():
    registry.reload()
    for mode in ("unified-LLM", "research", "paper", "computational-imaging"):
        spec = registry.get(mode)
        assert "compute-providers" in spec.capabilities, mode


# (git-transport tests removed in P4 — transport is HTTP-only; see
#  test_http_transport.py for the relay round-trip.)


def test_resolve_founder_gpu_prefers_registered_subgpu(tmp_path, monkeypatch):
    """Dispatching to the advertised `founder-gpu` via the agent must resolve to
    the REGISTERED founder-1-subgpu (git-synced inbox), not the built-in default's
    local inbox — so the request actually reaches the box."""
    from ai4science.harness import compute_tools as ct
    from ai4science.compute.registry import ComputeProvider, save_registry
    reg = tmp_path / "providers.json"
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(reg))
    git_inbox = str(tmp_path / "git-inbox")
    save_registry([ComputeProvider(
        provider_id="founder-1-subgpu", wallet_address=THIRD_FOUNDER_WALLET,
        endpoint_path=git_inbox, kind="gpu")])
    p = ct._resolve("founder-gpu")
    assert p is not None and p.provider_id == "founder-1-subgpu"
    assert p.endpoint_path == git_inbox     # the served inbox, not ~/.config/.../gpu


def test_resolve_founder_gpu_falls_back_to_default_when_unregistered(tmp_path, monkeypatch):
    """No registry → founder-gpu still resolves to the built-in default."""
    from ai4science.harness import compute_tools as ct
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "none.json"))
    monkeypatch.setenv("AI4SCIENCE_FOUNDER_INBOX", str(tmp_path / "inbox"))
    p = ct._resolve("founder-gpu")
    assert p is not None and p.provider_id == "founder-gpu"
