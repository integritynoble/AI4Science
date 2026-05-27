"""ai4science.reports.certificate — build a submission certificate (manifest + hash).

A v0.1 certificate is just:
  - the set of file paths in the package
  - per-file SHA256
  - the certificate hash itself (sha256 of the sorted (path, sha256) list)

The certificate is NOT a PWM mainnet promotion — it's the local manifest
the deterministic Physics Judge will sign over. Mainnet promotion is a
founders-multisig action, never auto-emitted by this CLI.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List


def sha256_file(p: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blob in iter(lambda: f.read(chunk), b""):
            h.update(blob)
    return h.hexdigest()


def build_certificate(files: List[Path], root: Path) -> Dict:
    """Compute per-file SHA256 + the overall certificate hash."""
    entries: List[Dict[str, str]] = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        entries.append({"path": rel, "sha256": sha256_file(f)})
    entries.sort(key=lambda e: e["path"])

    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    cert_hash = "0x" + hashlib.sha256(canonical).hexdigest()

    return {
        "schema_version": "0.1",
        "submission_id": root.name,
        "files": entries,
        "certificate_hash": cert_hash,
        "promotion_status": "testnet",
        "note": (
            "Mainnet promotion is a founders-multisig action, not emitted by this CLI. "
            "The Physics Judge verdict is the source of truth for the testnet listing."
        ),
    }
