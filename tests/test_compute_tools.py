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


# ── lease gating: 1 concurrent (one job at a time), 2nd refused ───────────
def test_dispatch_is_lease_gated_at_one(tmp_path, monkeypatch):
    # pytest is non-interactive: opt in the way scripts/CI do, so the paid-
    # dispatch autonomy guard lets the lease logic under test run
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", "1")
    disp = _tool("compute_dispatch").func
    r1 = disp(tmp_path, provider="founder-cpu", run_command="a", confirm=True)
    assert "Dispatched job" in r1
    # the single slot is now taken → a 2nd concurrent dispatch waits/refuses
    r2 = disp(tmp_path, provider="founder-cpu", run_command="b", confirm=True)
    assert "busy" in r2.lower() and "wait" in r2.lower()


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


# ── cross-machine git-sync: the request is pushed so the remote box gets it ──
def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def test_repo_of_detects_git_inbox(tmp_path, monkeypatch):
    from ai4science.harness import compute_tools as ct
    from ai4science.compute.founders import founder_providers
    # non-git inbox → None
    monkeypatch.setenv("AI4SCIENCE_FOUNDER_INBOX", str(tmp_path / "plain"))
    gpu = {p.provider_id: p for p in founder_providers()}["founder-gpu"]
    assert ct._repo_of(gpu) is None
    # git inbox → the repo root
    repo = tmp_path / "repo"; repo.mkdir()
    assert _git(repo, "init").returncode == 0
    monkeypatch.setenv("AI4SCIENCE_FOUNDER_INBOX", str(repo / "compute-inbox"))
    gpu2 = {p.provider_id: p for p in founder_providers()}["founder-gpu"]
    from pathlib import Path
    Path(gpu2.endpoint_path).mkdir(parents=True, exist_ok=True)  # dispatch_job mkdirs it IRL
    assert ct._repo_of(gpu2) == repo.resolve()


def test_dispatch_pushes_request_to_git_remote(tmp_path, monkeypatch):
    """A confirmed dispatch to a git-backed inbox commits+pushes the request —
    the fix for 'dispatch succeeded but the sub-GPU never gets the request'."""
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_AUTOCONFIRM", "1")
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "providers.json"))
    # bare origin + a working clone whose inbox is inside the repo
    bare = tmp_path / "origin.git"; bare.mkdir()
    assert _git(bare, "init", "--bare").returncode == 0
    clone = tmp_path / "clone"; clone.mkdir()
    _git(clone, "init")
    _git(clone, "config", "user.email", "t@t.t"); _git(clone, "config", "user.name", "t")
    _git(clone, "config", "commit.gpgsign", "false")
    _git(clone, "remote", "add", "origin", str(bare))
    (clone / "seed").write_text("x")
    _git(clone, "add", "-A"); _git(clone, "commit", "-m", "seed")
    _git(clone, "branch", "-M", "main"); _git(clone, "push", "-u", "origin", "main")

    monkeypatch.setenv("AI4SCIENCE_FOUNDER_INBOX", str(clone / "compute-inbox"))
    out = _tool("compute_dispatch").func(
        clone, provider="founder-gpu", run_command="python run.py", confirm=True)
    assert "Dispatched job" in out
    assert "pushed to the remote provider" in out.lower()
    # the request is committed locally and present on the bare origin
    log = _git(clone, "log", "--oneline").stdout
    assert "compute: dispatch job" in log
    files = _git(bare, "ls-tree", "-r", "--name-only", "main").stdout
    assert ".request.json" in files
