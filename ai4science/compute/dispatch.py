"""Job dispatch over the file-inbox handshake.

v1 reuses the same pattern the sub-GPU server already uses for
baseline_runs: the agent writes a job request into a shared directory the
provider polls; the provider writes an ack and a result back.

  <endpoint>/job_<id>.request.json   ← agent writes
  <endpoint>/job_<id>.ack.json       ← provider writes (accepted/started)
  <endpoint>/job_<id>.result.json    ← provider writes (manifest)

No network transport, no daemon. The provider side is out of scope here
(it runs on a separate GPU host); this module only writes requests and
reads back ack/result state.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ComputeJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    provider_id: str
    wallet_address: str
    workspace: str
    # Path of the workspace relative to the git repo root, when the workspace
    # lives inside the shared repo. Lets a provider on a DIFFERENT machine
    # resolve the workspace against its own repo checkout (the dispatcher's
    # absolute ``workspace`` won't exist cross-machine). Empty when the
    # workspace is not under a git repo (same-machine only).
    workspace_repo_relative: str = ""
    solver_code_path: str = "code/"
    run_command: str = "python code/run_solver.py"
    benchmark_id: str = ""
    dataset_ref: str = ""
    requested_at: str = Field(default_factory=_utcnow)
    max_runtime_s: int = 3600


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def dispatch_job(*, provider, workspace: Path, benchmark_id: str = "",
                 solver_code_path: str = "code/",
                 run_command: str = "python code/run_solver.py",
                 dataset_ref: str = "", max_runtime_s: int = 3600) -> ComputeJob:
    """Write a job request into the provider's endpoint directory."""
    ws_abs = Path(workspace).resolve()
    # If the workspace is inside a git repo, record its repo-relative path so a
    # provider on another machine can resolve it against its own checkout.
    ws_rel = ""
    try:
        from ai4science.compute import gitsync
        repo = gitsync.find_repo_root(ws_abs)
        if repo is not None:
            ws_rel = ws_abs.relative_to(repo).as_posix()
    except Exception:
        ws_rel = ""
    job = ComputeJob(
        job_id=new_job_id(),
        provider_id=provider.provider_id,
        wallet_address=provider.wallet_address,
        workspace=str(ws_abs),
        workspace_repo_relative=ws_rel,
        solver_code_path=solver_code_path,
        run_command=run_command,
        benchmark_id=benchmark_id,
        dataset_ref=dataset_ref,
        max_runtime_s=max_runtime_s,
    )
    endpoint = Path(provider.endpoint_path).expanduser()
    endpoint.mkdir(parents=True, exist_ok=True)
    req_path = endpoint / f"job_{job.job_id}.request.json"
    req_path.write_text(json.dumps(job.model_dump(), indent=2) + "\n", encoding="utf-8")
    return job


def job_state(endpoint_path: Path, job_id: str) -> Dict[str, Any]:
    """Read the request/ack/result files for a job and summarize state."""
    endpoint = Path(endpoint_path).expanduser()
    req = endpoint / f"job_{job_id}.request.json"
    ack = endpoint / f"job_{job_id}.ack.json"
    res = endpoint / f"job_{job_id}.result.json"

    state = "unknown"
    if res.exists():
        state = "completed"
    elif ack.exists():
        state = "acked"
    elif req.exists():
        state = "requested"
    else:
        state = "missing"

    out: Dict[str, Any] = {"job_id": job_id, "state": state}
    for label, p in (("request", req), ("ack", ack), ("result", res)):
        if p.exists():
            try:
                out[label] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                out[label] = {"_error": "malformed JSON"}
    return out


def read_result(endpoint_path: Path, job_id: str) -> Optional[Dict[str, Any]]:
    res = Path(endpoint_path).expanduser() / f"job_{job_id}.result.json"
    if not res.exists():
        return None
    try:
        return json.loads(res.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
