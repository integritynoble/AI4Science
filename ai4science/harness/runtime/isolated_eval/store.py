from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

from .errors import TamperDetected

#: Every way the boundary can be crossed has a name. Nothing fails silently.
INCIDENT_KINDS = (
    "artefact_edited_after_handoff",
    "artefact_added_after_handoff",
    "artefact_removed_after_handoff",
    "manifest_edited_after_handoff",
    "verdict_seal_broken",
    "verdict_missing",
    "network_attempt_refused",
    "boundary_violation",
    "store_access_refused",
)

_SEALED_MODE = 0o000     #: between evaluations the store is not openable
_OPEN_MODE = 0o700       #: the evaluator's own mode while it is working


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


class EvaluatorStore:
    """The evaluator's own directory. The agent is not given the path and, while
    sealed, the kernel refuses to open it.

    Two layers, because one is not enough:

    1. **Refusal.** ``chmod 0o000`` on the store root. A non-root process — even
       the owner — is denied traversal by the kernel, so an agent that guesses
       the path gets ``PermissionError``, not the score.
    2. **Detection.** Every verdict and the handoff manifest are sealed with an
       HMAC over a key that lives inside the store. If the boundary is crossed
       anyway (same-uid agent that chmods the directory back, a backup restored
       over it), reading the verdict raises :class:`TamperDetected` with the
       incident *named*.

    Layer 1 is only a true seal when the evaluator runs as a different user or in
    a different mount namespace; ``__init__`` accepts ``owner_uid`` for the
    deployment that does. Under one uid, layer 1 is a refusal a determined
    optimizer can undo and layer 2 is what catches it. See the module docs.
    """

    def __init__(self, root: Path, *, owner_uid: int | None = None):
        self._root = Path(root)
        self._owner_uid = owner_uid
        existed = self._root.exists()
        if not existed:
            self._root.mkdir(parents=True, exist_ok=True)
        with self.unsealed():
            (self._root / "verdicts").mkdir(exist_ok=True)
            key_path = self._root / "seal.key"
            if not key_path.exists():
                key_path.write_bytes(secrets.token_bytes(32))
                os.chmod(key_path, 0o600)
            if owner_uid is not None:
                try:
                    os.chown(self._root, owner_uid, -1)
                    os.chown(key_path, owner_uid, -1)
                except PermissionError:
                    pass   # not privileged enough to hand it over; layer 2 still holds

    # -- the boundary -----------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    def seal(self) -> None:
        """Close the store. After this an open by anyone unprivileged fails."""
        os.chmod(self._root, _SEALED_MODE)

    def is_sealed(self) -> bool:
        return (self._root.stat().st_mode & 0o777) == _SEALED_MODE

    @contextmanager
    def unsealed(self):
        """Evaluator-side only: open the store for the length of one operation."""
        os.chmod(self._root, _OPEN_MODE)
        try:
            yield self._root
        finally:
            self.seal()

    # -- seals ------------------------------------------------------------

    def _key(self) -> bytes:
        return (self._root / "seal.key").read_bytes()

    def _seal_of(self, payload: dict) -> str:
        return "hmac-sha256:" + hmac.new(self._key(), _canonical(payload),
                                         hashlib.sha256).hexdigest()

    @staticmethod
    def digest_of(payload: dict) -> str:
        """Content digest of a verdict payload; equal across runs iff the verdict is."""
        return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()

    # -- what the store holds ---------------------------------------------

    def put_handoff(self, run_id: str, handoff_dict: dict) -> None:
        with self.unsealed():
            self._write_sealed(self._root / f"handoff-{run_id}.json", handoff_dict)

    def get_handoff(self, run_id: str) -> dict:
        with self.unsealed():
            return self._read_sealed(self._root / f"handoff-{run_id}.json",
                                     run_id, "manifest_edited_after_handoff")

    def put_verdict(self, run_id: str, payload: dict) -> str:
        """Seal a verdict and return its content digest."""
        with self.unsealed():
            self._write_sealed(self._root / "verdicts" / f"{run_id}.json", payload)
        return self.digest_of(payload)

    def get_verdict(self, run_id: str) -> dict:
        with self.unsealed():
            return self._read_sealed(self._root / "verdicts" / f"{run_id}.json",
                                     run_id, "verdict_seal_broken")

    def _write_sealed(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps({"payload": payload, "seal": self._seal_of(payload)},
                                   sort_keys=True), encoding="utf-8")
        os.chmod(path, 0o600)

    def _read_sealed(self, path: Path, run_id: str, kind: str) -> dict:
        if not path.exists():
            raise TamperDetected("verdict_missing" if "verdict" in kind else kind,
                                 f"{run_id}: {path.name} is not in the store")
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            payload, seal = blob["payload"], blob["seal"]
        except Exception as exc:
            raise TamperDetected(kind, f"{run_id}: {path.name} is not a sealed record ({exc})")
        if not hmac.compare_digest(seal, self._seal_of(payload)):
            raise TamperDetected(
                kind, f"{run_id}: {path.name} carries seal {seal} but its contents seal to "
                      f"{self._seal_of(payload)}")
        return payload

    # -- incidents ---------------------------------------------------------

    def record_incident(self, run_id: str, kind: str, detail: str) -> None:
        if kind not in INCIDENT_KINDS:
            raise ValueError(f"unnamed incident kind {kind!r}")
        with self.unsealed():
            line = json.dumps({"run_id": run_id, "kind": kind, "detail": detail},
                              sort_keys=True)
            with (self._root / "incidents.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def incidents(self, run_id: str | None = None) -> list:
        with self.unsealed():
            path = self._root / "incidents.jsonl"
            if not path.exists():
                return []
            rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
        return [r for r in rows if run_id is None or r["run_id"] == run_id]
