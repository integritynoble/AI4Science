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
        "solver_stderr_tail": outcome.get("stderr_tail", ""),
        "provider": {
            "provider_id": provider.get("provider_id"),
            "wallet_address": provider.get("wallet_address"),
            "ran_at": _utcnow(),
            "wall_clock_s": round(wall_clock_s, 2),
            "device": provider.get("gpu_capability", {}).get("device", "unknown"),
        },
    }


HEARTBEAT_PREFIX = "heartbeat."
# A provider is considered offline if its last heartbeat is older than this.
DEFAULT_STALE_AFTER_S = 180


def heartbeat_path(inbox: Path, provider_id: str) -> Path:
    """Per-provider heartbeat file (distinct name so providers sharing a synced
    inbox never collide — same scheme as request/ack/result files)."""
    return Path(inbox).expanduser() / f"{HEARTBEAT_PREFIX}{provider_id}.json"


def write_heartbeat(inbox: Path, provider_id: str, *, kind: str = "gpu",
                    note: str = "") -> Path:
    """Stamp 'this provider's serve loop is alive now' into the inbox."""
    p = heartbeat_path(inbox, provider_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "provider_id": provider_id,
        "kind": kind,
        "ts": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "pid": os.getpid(),
        "note": note,
    }, indent=2) + "\n", encoding="utf-8")
    return p


def read_heartbeat(inbox: Path, provider_id: str) -> Optional[Dict[str, Any]]:
    p = heartbeat_path(inbox, provider_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def liveness(provider: Dict[str, Any], *, stale_after_s: int = DEFAULT_STALE_AFTER_S):
    """(state, age_s) for a provider: state is 'online' | 'offline'; age_s is the
    heartbeat age in seconds (None = never seen). Lets the dispatcher tell a user
    'GPU online' vs 'GPU offline — queued' instead of a silent `requested`."""
    inbox = Path(provider["endpoint_path"]).expanduser()
    hb = read_heartbeat(inbox, provider.get("provider_id", ""))
    if not hb or not hb.get("ts"):
        return ("offline", None)
    try:
        ts = dt.datetime.fromisoformat(str(hb["ts"]).rstrip("Z"))
    except Exception:
        return ("offline", None)
    age = max(0.0, (dt.datetime.utcnow() - ts).total_seconds())
    return ("online" if age <= stale_after_s else "offline", age)
