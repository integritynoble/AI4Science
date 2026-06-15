"""HTTP transport — dispatch/poll a compute job over the relay (no pwm repo).

Talks to the relay REST contract on physicsworldmodel.org
(``COMPUTE_HTTP_RELAY_DESIGN.md`` / pwm_nonprofit ``routers/compute.py``):

    POST /api/v1/compute/jobs          dispatch         (user bearer token)
    GET  /api/v1/compute/jobs/{id}     poll state/result

Phase 3: the workspace + reconstruction travel **inline** (base64 tar.gz in the
``workspace_ref`` / ``reconstruction_ref`` strings) so the whole path is provable
end-to-end with no cloud deps. Phase 2 swaps those for GCS presigned URLs — the
method seam (``_pack_workspace`` / ``_unpack_reconstruction``) stays the same.
"""
from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path
from typing import Any, Dict, Optional

INLINE_PREFIX = "inline:"
# Guardrail: inline is only for small workspaces (P3 proof). Bigger → use GCS (P2).
MAX_INLINE_BYTES = 2_000_000


def _pack_workspace(workspace: Path) -> str:
    """tar.gz a workspace dir → 'inline:<base64>'. Raises if too big for inline."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(workspace), arcname=".")
    raw = buf.getvalue()
    if len(raw) > MAX_INLINE_BYTES:
        raise ValueError(
            f"workspace is {len(raw)} bytes — too large for inline transport "
            f"(>{MAX_INLINE_BYTES}). Use the GCS data plane (Phase 2).")
    return INLINE_PREFIX + base64.b64encode(raw).decode("ascii")


def unpack_inline(ref: str, dest: Path) -> bool:
    """Extract an 'inline:<base64>' tar.gz into dest. False if ref isn't inline."""
    if not ref or not ref.startswith(INLINE_PREFIX):
        return False
    raw = base64.b64decode(ref[len(INLINE_PREFIX):])
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        tar.extractall(str(dest))
    return True


def pack_file(path: Path) -> str:
    """Pack a single result file → 'inline:<base64>' (the reconstruction)."""
    raw = Path(path).read_bytes()
    return INLINE_PREFIX + base64.b64encode(raw).decode("ascii")


class HttpTransport:
    """Client side of the relay. Reusable by the CLI, the agent tool, and tests."""

    def __init__(self, base_url: str, token: str = "", *, client: Optional[Any] = None,
                 timeout: float = 60.0):
        self.base = base_url.rstrip("/")
        self.token = token
        self._timeout = timeout
        self._client = client          # inject an httpx.Client in tests

    def _http(self):
        if self._client is not None:
            return self._client
        import httpx
        return httpx.Client(timeout=self._timeout)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def dispatch(self, *, provider_id: str, run_command: str, workspace: Path,
                 dataset_ref: str = "", max_runtime_s: int = 600) -> Dict[str, Any]:
        """Upload the workspace (inline) and create the job. Returns the job dict."""
        workspace_ref = _pack_workspace(Path(workspace))
        r = self._http().post(
            f"{self.base}/api/v1/compute/jobs",
            headers=self._headers(),
            json={"provider_id": provider_id, "run_command": run_command,
                  "workspace_ref": workspace_ref, "dataset_ref": dataset_ref,
                  "max_runtime_s": max_runtime_s})
        r.raise_for_status()
        return r.json()["job"]

    def poll(self, job_id: str) -> Dict[str, Any]:
        r = self._http().get(f"{self.base}/api/v1/compute/jobs/{job_id}",
                             headers=self._headers())
        r.raise_for_status()
        return r.json()["job"]

    def download_reconstruction(self, job: Dict[str, Any], dest_dir: Path) -> Optional[Path]:
        """Write the returned reconstruction into dest_dir/results/. Returns the
        path, or None if there was no inline reconstruction."""
        ref = job.get("reconstruction_ref") or ""
        if not ref.startswith(INLINE_PREFIX):
            return None
        raw = base64.b64decode(ref[len(INLINE_PREFIX):])
        out = Path(dest_dir) / "results" / "reconstruction_xhat.npy"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        return out
