"""Provider-side poller — runs on the GPU box.

Watches a provider's inbox directory for ``job_<id>.request.json`` files,
runs the dispatched solver on the GPU, and writes ``job_<id>.ack.json``
then ``job_<id>.result.json`` back.

This is the counterpart to ``ai4science compute dispatch``. The dispatch
side (agent) writes requests; this side (provider) fulfills them.

  inbox/job_<id>.request.json   ← dispatch writes
  inbox/job_<id>.ack.json       ← THIS writes (accepted, started)
  inbox/job_<id>.result.json    ← THIS writes (manifest + certificate)

SECURITY: this executes the ``run_command`` carried in a job request —
i.e. it runs dispatched code on your machine. Running requires the
explicit ``allow_exec=True`` gate (CLI: ``--allow-exec``). In Phase 0
the dispatcher is the founder, so it's trusted; community providers must
sandbox (see docs/COMPUTE_PROVIDERS_DESIGN.md §7).

Workspace assumption (Phase 0): the job's ``workspace`` path is reachable
from the GPU box (same machine or shared/synced filesystem), and the
solver reads data/ + writes results/reconstruction_xhat.npy there. True
remote execution (ship the workspace / pull from GCS) is a later phase.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _split_command(run_command: str) -> List[str]:
    """Split a shell-style command into argv, correctly on POSIX and Windows.

    On Windows, ``shlex.split`` in its default POSIX mode treats the
    backslashes in paths like ``C:\\Python\\python.exe`` as escape characters
    and silently destroys the path. Using ``posix=False`` preserves the path
    but leaves matched surrounding quotes on tokens (e.g. ``-c "code"`` keeps
    the quotes), so we strip a single matched pair afterward. subprocess then
    re-quotes each argv element correctly via list2cmdline.
    """
    posix = os.name != "nt"
    argv = shlex.split(run_command, posix=posix)
    if not posix:
        argv = [
            tok[1:-1] if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'" else tok
            for tok in argv
        ]
    return argv


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_file(p: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blob in iter(lambda: f.read(chunk), b""):
            h.update(blob)
    return h.hexdigest()


def pending_jobs(inbox: Path) -> List[Path]:
    """Request files that have no result yet (and no ack — not in flight)."""
    inbox = Path(inbox).expanduser()
    if not inbox.is_dir():
        return []
    out = []
    for req in sorted(inbox.glob("job_*.request.json")):
        job_id = req.name[len("job_"):-len(".request.json")]
        result = inbox / f"job_{job_id}.result.json"
        ack = inbox / f"job_{job_id}.ack.json"
        if not result.exists() and not ack.exists():
            out.append(req)
    return out


def compute_certificate_hash(workspace: Path, job: Dict[str, Any],
                             metrics: Dict[str, Any]) -> str:
    """Content-address the result: hash the reconstruction bytes + key fields."""
    recon = workspace / "results" / "reconstruction_xhat.npy"
    h = hashlib.sha256()
    if recon.exists():
        h.update(_sha256_file(recon).encode("utf-8"))
    canonical = json.dumps(
        {
            "job_id": job.get("job_id"),
            "benchmark_id": job.get("benchmark_id", ""),
            "wallet_address": job.get("wallet_address"),
            "metrics": metrics,
        },
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    h.update(canonical)
    return "0x" + h.hexdigest()


def _collect_metrics(workspace: Path) -> Dict[str, Any]:
    """Read results/results.json if the solver wrote one (claimed metrics)."""
    rj = workspace / "results" / "results.json"
    if rj.exists():
        try:
            return json.loads(rj.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def run_solver(workspace: Path, run_command: str, timeout_s: int) -> Dict[str, Any]:
    """Execute the solver command with cwd=workspace. Returns an outcome dict."""
    try:
        argv = _split_command(run_command)
    except ValueError as e:
        return {"ok": False, "error": f"could not parse run_command: {e}"}
    if not argv:
        return {"ok": False, "error": "empty run_command"}

    try:
        proc = subprocess.run(
            argv, cwd=str(workspace), capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"solver timed out after {timeout_s}s"}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": f"solver exec error: {type(e).__name__}: {e}"}

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def build_result_manifest(job: Dict[str, Any], workspace: Path,
                          provider: Dict[str, Any], outcome: Dict[str, Any],
                          wall_clock_s: float) -> Dict[str, Any]:
    """Assemble the result manifest the dispatcher / judge will consume."""
    metrics = _collect_metrics(workspace)
    cert = compute_certificate_hash(workspace, job, metrics)
    recon_rel = "results/reconstruction_xhat.npy"
    recon_exists = (workspace / recon_rel).exists()

    return {
        "job_id": job.get("job_id"),
        "benchmark_id": job.get("benchmark_id", ""),
        "solver_id": job.get("run_command", ""),
        "certificate_hash": cert,
        "metrics": metrics,
        "reconstruction_artifacts": [recon_rel] if recon_exists else [],
        "status": "testnet",
        "solver_ran": outcome.get("ok", False),
        "solver_returncode": outcome.get("returncode"),
        "solver_error": outcome.get("error"),
        "solver_stdout_tail": outcome.get("stdout_tail", ""),
        "provider": {
            "provider_id": provider.get("provider_id"),
            "wallet_address": provider.get("wallet_address"),
            "ran_at": _utcnow(),
            "wall_clock_s": round(wall_clock_s, 2),
            "device": provider.get("gpu_capability", {}).get("device", "unknown"),
        },
    }


def _resolve_workspace(job: Dict[str, Any], inbox: Path) -> Path:
    """Resolve the job's workspace on THIS host.

    Prefers the absolute ``workspace`` when it exists locally (same-machine
    dispatch). Otherwise, when ``workspace_repo_relative`` is set, resolves it
    against the local checkout of the shared repo (the one holding the inbox),
    so a job dispatched from another machine still finds its workspace.
    """
    abs_ws = Path(job.get("workspace", "")).expanduser()
    if abs_ws.is_dir():
        return abs_ws
    rel = (job.get("workspace_repo_relative") or "").strip()
    if rel:
        from ai4science.compute import gitsync
        repo = gitsync.find_repo_root(inbox)
        if repo is not None:
            candidate = repo / rel
            if candidate.is_dir():
                return candidate
    return abs_ws  # not reachable — caller reports a clear error


def process_job(req_path: Path, provider: Dict[str, Any],
                allow_exec: bool) -> Dict[str, Any]:
    """Ack, run the solver, and write the result for one job request."""
    inbox = req_path.parent
    job = json.loads(req_path.read_text(encoding="utf-8"))
    job_id = job["job_id"]

    # 1. Ack immediately so the dispatcher sees it's in flight.
    ack = {"job_id": job_id, "accepted": True, "started_at": _utcnow(),
           "provider_id": provider.get("provider_id")}
    (inbox / f"job_{job_id}.ack.json").write_text(json.dumps(ack, indent=2), encoding="utf-8")

    workspace = _resolve_workspace(job, inbox)
    t0 = time.monotonic()

    if not allow_exec:
        outcome = {"ok": False, "error": "execution disabled (start with --allow-exec)"}
    elif not workspace.is_dir():
        outcome = {"ok": False, "error": f"workspace not reachable on this host: {workspace}"}
    else:
        outcome = run_solver(workspace, job.get("run_command", ""),
                             int(job.get("max_runtime_s", 3600)))

    wall = time.monotonic() - t0
    manifest = build_result_manifest(job, workspace, provider, outcome, wall)
    (inbox / f"job_{job_id}.result.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def poll_once(provider: Dict[str, Any], allow_exec: bool) -> List[str]:
    """Process all currently-pending jobs once. Returns processed job ids."""
    inbox = Path(provider["endpoint_path"]).expanduser()
    processed: List[str] = []
    for req in pending_jobs(inbox):
        manifest = process_job(req, provider, allow_exec)
        processed.append(manifest["job_id"])
    return processed


def serve(provider: Dict[str, Any], *, interval_s: int = 5, once: bool = False,
          allow_exec: bool = False, git_sync: bool = False, on_event=None) -> None:
    """Poll loop. on_event(kind, payload) is an optional callback for logging.

    When ``git_sync`` is set, the inbox lives in a git repo shared with the
    dispatcher: each pass runs ``git pull`` before scanning (to receive new
    requests) and ``git add/commit/push`` after each result (to publish it).
    """
    inbox = Path(provider["endpoint_path"]).expanduser()
    inbox.mkdir(parents=True, exist_ok=True)

    def emit(kind: str, payload: Any):
        if on_event:
            on_event(kind, payload)

    repo = None
    if git_sync:
        from ai4science.compute import gitsync
        repo = gitsync.find_repo_root(inbox)
        if repo is None:
            emit("sync_warn", {"error": f"git-sync on but {inbox} is not in a git repo "
                                        "— falling back to local-only inbox"})

    emit("start", {"inbox": str(inbox), "allow_exec": allow_exec,
                   "git_sync": repo is not None})
    while True:
        if repo is not None:
            from ai4science.compute import gitsync
            ok, msg = gitsync.pull(repo)
            emit("sync_pull", {"ok": ok, "msg": msg})
        for req in pending_jobs(inbox):
            job_id = req.name[len("job_"):-len(".request.json")]
            emit("job_start", {"job_id": job_id})
            try:
                manifest = process_job(req, provider, allow_exec)
                emit("job_done", {"job_id": job_id,
                                  "solver_ran": manifest.get("solver_ran"),
                                  "certificate_hash": manifest.get("certificate_hash")})
                if repo is not None:
                    from ai4science.compute import gitsync
                    files = [inbox / f"job_{job_id}.ack.json",
                             inbox / f"job_{job_id}.result.json"]
                    ok, msg = gitsync.commit_push(
                        repo, files,
                        f"compute: result for job {job_id} "
                        f"({provider.get('provider_id', '?')})")
                    emit("sync_push", {"job_id": job_id, "ok": ok, "msg": msg})
            except Exception as e:  # never let one bad job kill the poller
                emit("job_error", {"job_id": job_id, "error": f"{type(e).__name__}: {e}"})
        if once:
            break
        time.sleep(interval_s)
