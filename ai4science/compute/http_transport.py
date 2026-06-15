"""HTTP transport — dispatch/poll a compute job over the relay (no pwm repo).

Talks to the relay REST contract (``COMPUTE_HTTP_RELAY_DESIGN.md`` /
pwm_nonprofit ``routers/compute.py``):

    POST /api/v1/compute/jobs          dispatch
    GET  /api/v1/compute/jobs/{id}     poll
    POST /api/v1/compute/blobs         upload an artifact (data plane)
    GET  /api/v1/compute/blobs/{key}   download an artifact

Data plane (Phase 2): the workspace + reconstruction move through the
**authenticated blob proxy** to GCS (signed URLs are disabled in this GCP
project), referenced as ``gcs:<key>``. The legacy ``inline:<base64>`` form is
still understood on unpack for back-compat / tiny jobs.
"""
from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path
from typing import Any, Dict, Optional

INLINE_PREFIX = "inline:"
GCS_PREFIX = "gcs:"


# ── tar helpers ─────────────────────────────────────────────────────────────
def tar_workspace(workspace: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(workspace), arcname=".")
    return buf.getvalue()


def untar_to(raw: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        tar.extractall(str(dest))


def unpack_workspace_ref(ref: str, dest: Path, *, http=None) -> bool:
    """Materialize a workspace from a gcs:/inline: ref into dest. False if neither."""
    if ref.startswith(GCS_PREFIX):
        untar_to(http.download_blob(ref[len(GCS_PREFIX):]), dest)
        return True
    if ref.startswith(INLINE_PREFIX):
        untar_to(base64.b64decode(ref[len(INLINE_PREFIX):]), dest)
        return True
    return False


class HttpTransport:
    """Client side of the relay. Reusable by the CLI, the agent tool, and tests."""

    def __init__(self, base_url: str, token: str = "", *, client: Optional[Any] = None,
                 provider_key: str = "", timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        self.token = token
        self.provider_key = provider_key
        self._timeout = timeout
        self._client = client          # inject an httpx.Client in tests

    def _http(self):
        if self._client is not None:
            return self._client
        import httpx
        return httpx.Client(timeout=self._timeout)

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.provider_key:
            h["X-Provider-Key"] = self.provider_key
        return h

    # ── data plane (blob proxy) ──────────────────────────────────────────
    def upload_blob(self, data: bytes) -> str:
        """Upload raw bytes → return the storage key."""
        r = self._http().post(f"{self.base}/api/v1/compute/blobs",
                              headers=self._headers(), content=data)
        r.raise_for_status()
        return r.json()["key"]

    def download_blob(self, key: str) -> bytes:
        r = self._http().get(f"{self.base}/api/v1/compute/blobs/{key}",
                             headers=self._headers())
        r.raise_for_status()
        return r.content

    # ── control plane ────────────────────────────────────────────────────
    def dispatch(self, *, provider_id: str, run_command: str, workspace: Path,
                 dataset_ref: str = "", max_runtime_s: int = 600) -> Dict[str, Any]:
        """Upload the workspace via the blob proxy, then create the job."""
        key = self.upload_blob(tar_workspace(Path(workspace)))
        r = self._http().post(
            f"{self.base}/api/v1/compute/jobs", headers=self._headers(),
            json={"provider_id": provider_id, "run_command": run_command,
                  "workspace_ref": GCS_PREFIX + key, "dataset_ref": dataset_ref,
                  "max_runtime_s": max_runtime_s})
        r.raise_for_status()
        return r.json()["job"]

    def poll(self, job_id: str) -> Dict[str, Any]:
        r = self._http().get(f"{self.base}/api/v1/compute/jobs/{job_id}",
                             headers=self._headers())
        r.raise_for_status()
        return r.json()["job"]

    def download_reconstruction(self, job: Dict[str, Any], dest_dir: Path) -> Optional[Path]:
        """Write the returned reconstruction into dest_dir/results/. None if absent."""
        ref = job.get("reconstruction_ref") or ""
        if ref.startswith(GCS_PREFIX):
            raw = self.download_blob(ref[len(GCS_PREFIX):])
        elif ref.startswith(INLINE_PREFIX):
            raw = base64.b64decode(ref[len(INLINE_PREFIX):])
        else:
            return None
        out = Path(dest_dir) / "results" / "reconstruction_xhat.npy"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        return out
