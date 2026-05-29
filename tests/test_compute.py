"""Tests for the compute layer: registry, dispatch, attribution."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from ai4science.cli import app
from ai4science.compute import (
    ComputeProvider, is_valid_eth_address, add_provider, load_registry,
)
from ai4science.compute.registry import get_provider
from ai4science.compute.dispatch import dispatch_job, job_state, new_job_id
from ai4science.compute.attribution import (
    verify_and_attribute, credit_summary, read_attributions,
)

runner = CliRunner()

DIRECTOR_WALLET = "0xf1Fa5803daAAaFf89932592ad54F4e7F5e3f7DEE"


# ─── Address validation ──────────────────────────────────────────────


def test_valid_director_address():
    assert is_valid_eth_address(DIRECTOR_WALLET) is True


def test_invalid_addresses_rejected():
    assert not is_valid_eth_address("0x123")             # too short
    assert not is_valid_eth_address("f1Fa5803" * 5)      # no 0x
    assert not is_valid_eth_address("0x" + "z" * 40)     # non-hex
    assert not is_valid_eth_address("")
    assert not is_valid_eth_address(None)  # type: ignore


def test_provider_rejects_bad_address():
    with pytest.raises(ValueError, match="invalid Ethereum address"):
        ComputeProvider(provider_id="x", wallet_address="nope",
                        endpoint_path="/tmp/x")


def test_provider_preserves_checksum_casing():
    p = ComputeProvider(provider_id="prov", wallet_address=DIRECTOR_WALLET,
                        endpoint_path="/tmp/x")
    assert p.wallet_address == DIRECTOR_WALLET   # exact casing preserved


# ─── Registry roundtrip ──────────────────────────────────────────────


def test_registry_add_load_get(tmp_path):
    reg = tmp_path / "providers.json"
    p = ComputeProvider(provider_id="founder-1-subgpu",
                        wallet_address=DIRECTOR_WALLET,
                        endpoint_path=str(tmp_path / "jobs"),
                        trust_tier="founder")
    add_provider(p, path=reg)
    loaded = load_registry(reg)
    assert len(loaded) == 1
    assert loaded[0].provider_id == "founder-1-subgpu"
    assert loaded[0].wallet_address == DIRECTOR_WALLET
    assert get_provider("founder-1-subgpu", reg).trust_tier == "founder"


def test_registry_replace_by_id(tmp_path):
    reg = tmp_path / "providers.json"
    add_provider(ComputeProvider(provider_id="prov", wallet_address=DIRECTOR_WALLET,
                                 endpoint_path="/tmp/a"), path=reg)
    add_provider(ComputeProvider(provider_id="prov", wallet_address=DIRECTOR_WALLET,
                                 endpoint_path="/tmp/b", status="disabled"), path=reg)
    loaded = load_registry(reg)
    assert len(loaded) == 1            # replaced, not duplicated
    assert loaded[0].endpoint_path == "/tmp/b"
    assert loaded[0].status == "disabled"


# ─── Dispatch handshake ──────────────────────────────────────────────


def _provider(tmp_path) -> ComputeProvider:
    return ComputeProvider(provider_id="founder-1-subgpu",
                           wallet_address=DIRECTOR_WALLET,
                           endpoint_path=str(tmp_path / "jobs"))


def test_dispatch_writes_request(tmp_path):
    prov = _provider(tmp_path)
    job = dispatch_job(provider=prov, workspace=tmp_path, benchmark_id="L3-003-001-001-T1")
    req = Path(prov.endpoint_path) / f"job_{job.job_id}.request.json"
    assert req.exists()
    data = json.loads(req.read_text())
    assert data["wallet_address"] == DIRECTOR_WALLET
    assert data["benchmark_id"] == "L3-003-001-001-T1"


def test_job_state_transitions(tmp_path):
    prov = _provider(tmp_path)
    job = dispatch_job(provider=prov, workspace=tmp_path)
    endpoint = Path(prov.endpoint_path)

    assert job_state(endpoint, job.job_id)["state"] == "requested"

    (endpoint / f"job_{job.job_id}.ack.json").write_text('{"accepted": true}')
    assert job_state(endpoint, job.job_id)["state"] == "acked"

    (endpoint / f"job_{job.job_id}.result.json").write_text(
        '{"certificate_hash": "0xabc", "metrics": {"PSNR": 30}}')
    st = job_state(endpoint, job.job_id)
    assert st["state"] == "completed"
    assert st["result"]["certificate_hash"] == "0xabc"


def test_job_state_missing(tmp_path):
    assert job_state(tmp_path / "jobs", "nope")["state"] == "missing"


# ─── Attribution (judge re-verification) ─────────────────────────────


def _init_demo(tmp_path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    # Isolate the canonical attribution ledger so tests never touch ~/.config.
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_LEDGER", str(tmp_path / "ledger.jsonl"))
    r = runner.invoke(app, ["init", "demo"])
    assert r.exit_code == 0, r.output
    return tmp_path / "demo"


def _make_cassi_arrays(ws: Path, good: bool):
    """Create measurement + reconstruction. good=True → near-perfect recon
    (passes S4); good=False → zeros (silent failure)."""
    from ai4science.judge.cassi.forward import cassi_forward
    rng = np.random.default_rng(0)
    H, W, C = 16, 16, 4
    x = rng.uniform(0.1, 0.9, size=(H, W, C))
    mask = (rng.random((H, W)) > 0.5).astype(float)
    y = cassi_forward(x, mask) + rng.normal(0, 0.01, size=(H, W + C - 1))
    (ws / "data").mkdir(exist_ok=True)
    (ws / "results").mkdir(exist_ok=True)
    np.save(ws / "data" / "measurement_y.npy", y)
    np.save(ws / "data" / "coded_aperture_phi.npy", mask)
    np.save(ws / "results" / "reconstruction_xhat.npy",
            x if good else np.zeros_like(x))


def test_attribution_awards_credit_on_pass(tmp_path, monkeypatch):
    ws = _init_demo(tmp_path, monkeypatch)
    _make_cassi_arrays(ws, good=True)
    job = {"job_id": "j1", "provider_id": "founder-1-subgpu",
           "wallet_address": DIRECTOR_WALLET, "benchmark_id": "T1"}
    attr = verify_and_attribute(workspace=ws, job=job,
                                result_manifest={"certificate_hash": "0xabc"})
    assert attr["judge_decision"] == "pass"
    assert attr["credit"] == 1
    assert attr["wallet_address"] == DIRECTOR_WALLET


def test_attribution_no_credit_on_silent_failure(tmp_path, monkeypatch):
    ws = _init_demo(tmp_path, monkeypatch)
    _make_cassi_arrays(ws, good=False)   # zeros → S4 fails
    job = {"job_id": "j2", "provider_id": "founder-1-subgpu",
           "wallet_address": DIRECTOR_WALLET}
    attr = verify_and_attribute(workspace=ws, job=job)
    assert attr["credit"] == 0
    assert attr["judge_decision"] in ("fail", "needs_review")


def test_credit_summary_aggregates_by_wallet(tmp_path, monkeypatch):
    ws = _init_demo(tmp_path, monkeypatch)
    _make_cassi_arrays(ws, good=True)
    job = {"job_id": "j", "provider_id": "p", "wallet_address": DIRECTOR_WALLET}
    verify_and_attribute(workspace=ws, job=job)
    verify_and_attribute(workspace=ws, job=job)
    totals = credit_summary(ws)
    assert totals[DIRECTOR_WALLET] == 2
    assert len(read_attributions(ws)) == 2


def test_canonical_ledger_aggregates_across_workspaces(tmp_path, monkeypatch):
    """Attributions written from different workspaces all land in the canonical
    ledger, so credit_summary() (no arg) aggregates them — the bug that made
    `compute credits` show 0 after a verify run in a different cwd."""
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_LEDGER", str(tmp_path / "ledger.jsonl"))
    from ai4science.compute.attribution import default_ledger_path

    # Two separate workspaces, each producing a passing attribution.
    for name in ("wsA", "wsB"):
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["init", name])
        assert r.exit_code == 0, r.output
        ws = tmp_path / name
        _make_cassi_arrays(ws, good=True)
        job = {"job_id": name, "provider_id": "p", "wallet_address": DIRECTOR_WALLET}
        attr = verify_and_attribute(workspace=ws, job=job)
        assert attr["credit"] == 1

    # Canonical ledger (source=None) sees BOTH; each workspace-local log sees one.
    assert default_ledger_path() == tmp_path / "ledger.jsonl"
    assert credit_summary()[DIRECTOR_WALLET] == 2          # aggregate
    assert credit_summary(tmp_path / "wsA")[DIRECTOR_WALLET] == 1  # local copy


def test_verify_defaults_workspace_to_job_request(tmp_path, monkeypatch):
    """`compute verify` with no -w judges the job request's stored workspace,
    not the caller's cwd (the bug that produced a false 'fail')."""
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "reg.json"))
    monkeypatch.chdir(tmp_path)
    # provider + workspace
    runner.invoke(app, ["compute", "providers-add", "--id", "founder-1-subgpu",
                        "--wallet", DIRECTOR_WALLET, "--endpoint", str(tmp_path / "jobs"),
                        "--tier", "founder"])
    runner.invoke(app, ["init", "solvews"])
    ws = tmp_path / "solvews"
    _make_cassi_arrays(ws, good=True)
    # dispatch a job that records ws as its workspace
    from ai4science.compute.dispatch import dispatch_job
    from ai4science.compute.registry import get_provider
    prov = get_provider("founder-1-subgpu")
    job = dispatch_job(provider=prov, workspace=ws, run_command="true")
    # write a result so job_state has one (poller would normally do this)
    (Path(prov.endpoint_path) / f"job_{job.job_id}.result.json").write_text(
        '{"certificate_hash": "0xfeed"}', encoding="utf-8")
    # verify from a DIFFERENT cwd, no -w → must still judge ws (pass), not cwd
    monkeypatch.chdir(tmp_path)   # cwd has no spec.md
    r = runner.invoke(app, ["compute", "verify", job.job_id,
                            "--provider", "founder-1-subgpu"])
    assert r.exit_code == 0, r.output
    assert "pass" in r.output.lower()
    # whitespace-normalized so Rich line-wrapping (e.g. "from\njob request")
    # doesn't break the substring check
    assert "from job request" in " ".join(r.output.split())


# ─── Cross-machine workspace resolution ──────────────────────────────


def _git_init(repo: Path):
    import subprocess
    repo.mkdir(parents=True, exist_ok=True)
    for args in (["init", "-q"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True,
                       capture_output=True)


def test_dispatch_records_repo_relative_workspace(tmp_path):
    """A workspace inside a git repo gets its repo-relative path stored, so a
    provider on another machine can resolve it against its own checkout."""
    repo = tmp_path / "repo"
    _git_init(repo)
    ws = repo / "pwm-team" / "compute_jobs" / "ws" / "job1"
    ws.mkdir(parents=True)
    endpoint = repo / "pwm-team" / "compute_jobs"

    class _Prov:
        provider_id = "founder-1-subgpu"
        wallet_address = DIRECTOR_WALLET
        endpoint_path = str(endpoint)

    job = dispatch_job(provider=_Prov(), workspace=ws)
    req = json.loads((endpoint / f"job_{job.job_id}.request.json").read_text())
    assert req["workspace_repo_relative"] == "pwm-team/compute_jobs/ws/job1"


def test_resolve_workspace_uses_repo_relative_when_abs_missing(tmp_path):
    """The poller resolves a workspace it can't find at the dispatcher's
    absolute path by joining repo-relative against its own repo root."""
    from ai4science.compute.provider import _resolve_workspace
    repo = tmp_path / "repo"
    _git_init(repo)
    ws = repo / "pwm-team" / "compute_jobs" / "ws" / "job1"
    ws.mkdir(parents=True)
    inbox = repo / "pwm-team" / "compute_jobs"

    job = {
        "workspace": "/nonexistent/dispatcher/path/ws/job1",   # other machine
        "workspace_repo_relative": "pwm-team/compute_jobs/ws/job1",
    }
    resolved = _resolve_workspace(job, inbox)
    assert resolved.resolve() == ws.resolve()


def test_resolve_workspace_prefers_local_abs_when_present(tmp_path):
    """Same-machine dispatch: the absolute workspace exists, so it's used as-is."""
    from ai4science.compute.provider import _resolve_workspace
    ws = tmp_path / "local_ws"
    ws.mkdir()
    job = {"workspace": str(ws), "workspace_repo_relative": "ignored/when/abs/exists"}
    assert _resolve_workspace(job, tmp_path).resolve() == ws.resolve()


def test_verify_resolves_foreign_workspace_via_repo_relative(tmp_path, monkeypatch):
    """`compute verify` (no -w) resolves a FOREIGN absolute workspace via the
    repo-relative path against this machine's checkout — independent
    verification works cross-machine without -w."""
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "reg.json"))
    repo = tmp_path / "repo"
    _git_init(repo)
    endpoint = repo / "pwm-team" / "compute_jobs"
    endpoint.mkdir(parents=True)
    # init the solve workspace UNDER the repo, with a passing reconstruction
    monkeypatch.chdir(endpoint)
    runner.invoke(app, ["init", "ws1"])
    ws = endpoint / "ws1"
    _make_cassi_arrays(ws, good=True)

    runner.invoke(app, ["compute", "providers-add", "--id", "founder-1-subgpu",
                        "--wallet", DIRECTOR_WALLET, "--endpoint", str(endpoint),
                        "--tier", "founder"])
    # a job whose stored absolute workspace is a FOREIGN path, but repo-relative
    # points at ws1 under this repo
    from ai4science.compute.dispatch import ComputeJob
    rel = ws.relative_to(repo).as_posix()
    job = ComputeJob(job_id="jx", provider_id="founder-1-subgpu",
                     wallet_address=DIRECTOR_WALLET,
                     workspace="/home/othermachine/pwm/ws1",
                     workspace_repo_relative=rel, run_command="true")
    (endpoint / "job_jx.request.json").write_text(
        json.dumps(job.model_dump(), indent=2), encoding="utf-8")
    (endpoint / "job_jx.result.json").write_text(
        '{"certificate_hash": "0xfeed"}', encoding="utf-8")

    monkeypatch.chdir(tmp_path)   # foreign cwd, no spec.md
    r = runner.invoke(app, ["compute", "verify", "jx", "--provider", "founder-1-subgpu"])
    assert r.exit_code == 0, r.output
    assert "pass" in r.output.lower()
    assert "via repo-relative" in r.output


def test_poller_commits_workspace_results_when_under_repo(tmp_path, monkeypatch):
    """serve --git-sync also commits ws/<job>/results/ so the dispatcher can
    re-verify the reconstruction. Captures the commit file list via a mock."""
    import numpy as np
    from ai4science.compute import provider as prov_mod
    repo = tmp_path / "repo"
    _git_init(repo)
    inbox = repo / "pwm-team" / "compute_jobs"
    ws = inbox / "ws" / "job1"
    (ws / "results").mkdir(parents=True)
    np.save(ws / "results" / "reconstruction_xhat.npy", np.ones((4, 4, 2), dtype=np.float32))
    (ws / "results" / "results.json").write_text("{}", encoding="utf-8")
    # a request whose workspace resolves (abs == ws, under repo)
    (inbox / "job_job1.request.json").write_text(json.dumps({
        "job_id": "job1", "provider_id": "founder-1-subgpu",
        "workspace": str(ws), "workspace_repo_relative": "pwm-team/compute_jobs/ws/job1",
        "run_command": "true",
    }), encoding="utf-8")

    captured = {}

    def _fake_commit_push(repo_arg, files, message):
        captured["files"] = [Path(f) for f in files]
        return True, "mocked"

    from ai4science.compute import gitsync as gitsync_mod
    monkeypatch.setattr(gitsync_mod, "find_repo_root", lambda p: repo)
    monkeypatch.setattr(gitsync_mod, "pull", lambda r: (True, ""))
    monkeypatch.setattr(gitsync_mod, "commit_push", _fake_commit_push)
    # don't actually run a solver
    monkeypatch.setattr(prov_mod, "run_solver",
                        lambda ws_, cmd, t: {"ok": True, "returncode": 0,
                                             "stdout_tail": "", "stderr_tail": ""})

    provider = {"provider_id": "founder-1-subgpu", "endpoint_path": str(inbox),
                "wallet_address": DIRECTOR_WALLET}
    prov_mod.serve(provider, once=True, allow_exec=True, git_sync=True)

    committed = {p.name for p in captured.get("files", [])}
    assert "job_job1.result.json" in committed
    assert "reconstruction_xhat.npy" in committed   # workspace results synced


# ─── CLI surface ─────────────────────────────────────────────────────


def test_cli_providers_add_rejects_bad_wallet(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "reg.json"))
    r = runner.invoke(app, ["compute", "providers-add", "--id", "x",
                            "--wallet", "not-an-address", "--endpoint", "/tmp/j"])
    assert r.exit_code == 2
    assert "invalid wallet" in r.output.lower()


def test_cli_providers_add_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "reg.json"))
    r = runner.invoke(app, ["compute", "providers-add",
                            "--id", "founder-1-subgpu",
                            "--wallet", DIRECTOR_WALLET,
                            "--endpoint", str(tmp_path / "jobs"),
                            "--tier", "founder"])
    assert r.exit_code == 0, r.output
    assert "founder-1-subgpu" in r.output
    r2 = runner.invoke(app, ["compute", "providers"])
    assert "founder-1-subgpu" in r2.output
    assert DIRECTOR_WALLET[:10] in r2.output
