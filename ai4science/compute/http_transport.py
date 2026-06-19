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
# A job workspace is the solver code + its inputs — NOT a home/project root. Skip
# environments, caches, and VCS so dispatching from a big cwd never tars hundreds
# of MB (e.g. the .ai4science venv). Cap the packed size with a clear error.
_TAR_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", ".ai4science", ".venv", "venv", "env", ".env",
    "node_modules", "__pycache__", ".cache", ".local", ".config", ".npm",
    ".mozilla", ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages",
}
MAX_WORKSPACE_BYTES = 100_000_000   # 100 MB packed


def _tar_filter(ti: "tarfile.TarInfo"):
    parts = set(Path(ti.name).parts)
    if parts & _TAR_EXCLUDE_DIRS:
        return None
    if ti.name.endswith((".pyc", ".pyo")):
        return None
    return ti


def tar_workspace(workspace: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(workspace), arcname=".", filter=_tar_filter)
    raw = buf.getvalue()
    if len(raw) > MAX_WORKSPACE_BYTES:
        raise ValueError(
            f"workspace packs to ~{len(raw) // 1_000_000} MB (> "
            f"{MAX_WORKSPACE_BYTES // 1_000_000} MB cap) even after excluding "
            "venvs/caches. Dispatch from a focused job dir (the solver code + its "
            "inputs), e.g. `cd` into the workspace `ai4science init` created — not "
            "a home or large project root.")
    return raw


def untar_to(raw: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        tar.extractall(str(dest))


def _is_excluded(p: Path) -> bool:
    parts = set(p.parts)
    return bool(parts & _TAR_EXCLUDE_DIRS) or p.name.endswith((".pyc", ".pyo"))


# Top-level workspace dirs that are INPUTS, not outputs — never returned: the
# shipped solver code and any (often huge) downloaded datasets.
_ARTIFACT_SKIP_TOP = {
    "code", "data", "datasets", "dataset", "raw", ".data", "input", "inputs",
}


def pack_artifacts(workspace: Path, *, max_bytes: int = 190_000_000):
    """Pack everything a job WROTE — runs/, results/, checkpoints, logs, *.pt,
    anywhere in the workspace EXCEPT the shipped code/ + data/ inputs and
    venv/caches — so trained checkpoints come back regardless of the script's
    output layout. Returns (bytes, [relative names]) or None if nothing was
    written. Raises ValueError over max_bytes (the blob ceiling)."""
    workspace = Path(workspace)
    if not workspace.is_dir():
        return None
    members = []
    for top in workspace.iterdir():
        if top.name in _ARTIFACT_SKIP_TOP or top.name in _TAR_EXCLUDE_DIRS:
            continue
        if top.is_dir():
            members += [p for p in top.rglob("*") if p.is_file() and not _is_excluded(p)]
        elif top.is_file() and not _is_excluded(top):
            members.append(top)
    if not members:
        return None
    names = sorted(str(p.relative_to(workspace)) for p in members)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in members:
            tar.add(str(p), arcname=str(p.relative_to(workspace)))
    raw = buf.getvalue()
    if len(raw) > max_bytes:
        raise ValueError(
            f"outputs pack to ~{len(raw) // 1_000_000} MB (> "
            f"{max_bytes // 1_000_000} MB cap) — too large to return over the "
            "relay; write smaller/fewer artifacts, or keep datasets in data/.")
    return raw, names


def pack_dir(path: Path, *, max_bytes: int = 190_000_000):
    """Gzip-tar a directory's contents (arcnames relative to it) for artifact
    return. Returns (bytes, [relative file names]) or None if the directory is
    missing/empty. Raises ValueError if it exceeds max_bytes (the blob ceiling)."""
    path = Path(path)
    if not path.is_dir():
        return None
    files = sorted(str(p.relative_to(path)) for p in path.rglob("*")
                   if p.is_file() and not _is_excluded(p))
    if not files:
        return None
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(path), arcname=".", filter=_tar_filter)
    raw = buf.getvalue()
    if len(raw) > max_bytes:
        raise ValueError(
            f"outputs pack to ~{len(raw) // 1_000_000} MB (> "
            f"{max_bytes // 1_000_000} MB cap) — too large to return over the "
            "relay; write smaller/fewer artifacts to results/.")
    return raw, files


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

    def fetch_artifacts(self, job: Dict[str, Any], dest_dir: Path) -> list:
        """Download + extract ALL output artifacts (everything the job wrote to
        results/ — trained checkpoints, logs, recon) into dest_dir. Returns the
        list of extracted relative file paths; empty if the job returned none."""
        result = job.get("result") or {}
        ref = result.get("artifacts_ref") or ""
        if ref.startswith(GCS_PREFIX):
            raw = self.download_blob(ref[len(GCS_PREFIX):])
        elif ref.startswith(INLINE_PREFIX):
            raw = base64.b64decode(ref[len(INLINE_PREFIX):])
        else:
            return []
        dest = Path(dest_dir)
        untar_to(raw, dest)
        return sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
