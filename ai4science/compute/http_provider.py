"""Provider-side HTTP serve loop — claim/run/return over the relay (no pwm repo).

The HTTP counterpart to ``provider.serve`` (the git poller). Each pass:
  1. POST heartbeat (liveness).
  2. GET /claim — atomically lease the next requested job (204 = none).
  3. Unpack the inline workspace, run the solver (reusing run_solver +
     build_result_manifest), pack the reconstruction inline.
  4. POST /jobs/{id}/result.

Phase 3 carries the workspace/reconstruction inline; Phase 2 swaps to GCS
presigned URLs (the pack/unpack seam in http_transport stays the same).
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ai4science.compute import http_transport as ht
from ai4science.compute.provider import run_solver, build_result_manifest


def _emit(on_event, kind, payload):
    if on_event:
        on_event(kind, payload)


def serve_http_once(provider: Dict[str, Any], base_url: str, *, provider_key: str = "",
                    allow_exec: bool = False, client: Optional[Any] = None,
                    on_event: Optional[Callable] = None) -> Optional[str]:
    """Process at most one job. Returns the job_id handled, or None if idle."""
    base = base_url.rstrip("/")
    pid = provider.get("provider_id", "")
    headers = {"X-Provider-Key": provider_key} if provider_key else {}

    def _http():
        if client is not None:
            return client
        import httpx
        return httpx.Client(timeout=120.0)

    h = _http()
    # the provider authenticates to the blob proxy with its key
    htx = ht.HttpTransport(base, provider_key=provider_key, client=h)

    # 1. heartbeat
    try:
        h.post(f"{base}/api/v1/compute/providers/{pid}/heartbeat", headers=headers)
    except Exception as e:
        _emit(on_event, "heartbeat_error", {"error": str(e)})

    # 2. claim
    r = h.get(f"{base}/api/v1/compute/claim", params={"provider_id": pid}, headers=headers)
    if r.status_code == 204:
        return None
    r.raise_for_status()
    job = r.json()["job"]
    job_id = job["job_id"]
    _emit(on_event, "job_start", {"job_id": job_id})

    # 3. run in an isolated temp workspace
    with tempfile.TemporaryDirectory(prefix=f"a4s-http-{job_id}-") as tmp:
        ws = Path(tmp)
        ht.unpack_workspace_ref(job.get("workspace_ref", ""), ws, http=htx)
        if not allow_exec:
            outcome = {"ok": False, "error": "provider running without --allow-exec"}
            wall = 0.0
        else:
            t0 = time.time()
            outcome = run_solver(ws, job.get("run_command", ""),
                                 int(job.get("max_runtime_s", 600)))
            wall = round(time.time() - t0, 2)
        manifest = build_result_manifest(job, ws, provider, outcome, wall)

        recon = ws / "results" / "reconstruction_xhat.npy"
        recon_ref = (ht.GCS_PREFIX + htx.upload_blob(recon.read_bytes())
                     if recon.exists() else "")

    # 4. return the result
    rr = h.post(f"{base}/api/v1/compute/jobs/{job_id}/result", headers=headers,
                json={"provider_id": pid, "result": manifest,
                      "reconstruction_ref": recon_ref})
    rr.raise_for_status()
    _emit(on_event, "job_done", {"job_id": job_id,
                                 "solver_ran": manifest.get("solver_ran"),
                                 "cert": manifest.get("certificate_hash")})
    return job_id


def serve_http(provider: Dict[str, Any], base_url: str, *, provider_key: str = "",
               allow_exec: bool = False, interval_s: int = 5, once: bool = False,
               on_event: Optional[Callable] = None) -> None:
    """Poll loop over HTTP. Mirrors provider.serve but needs no git repo."""
    _emit(on_event, "start", {"base": base_url, "provider": provider.get("provider_id")})
    while True:
        try:
            handled = serve_http_once(provider, base_url, provider_key=provider_key,
                                      allow_exec=allow_exec, on_event=on_event)
        except Exception as e:                 # never let one bad pass kill the loop
            _emit(on_event, "loop_error", {"error": f"{type(e).__name__}: {e}"})
            handled = None
        if once:
            break
        if handled is None:
            time.sleep(interval_s)
