from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import TamperDetected

#: Files the agent may leave lying about that are never part of a handoff.
_SKIP_NAMES = {"__pycache__", ".git", ".pytest_cache"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def manifest_digest(files: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical(files)).hexdigest()


@dataclass(frozen=True)
class Handoff:
    """What the agent handed over, and the digest of it at the moment it did."""

    run_id: str
    root: Path            #: the snapshot the evaluator reads; not the agent's live tree
    files: dict           #: {relative path: {"sha256": ..., "size": ...}}
    digest: str           #: digest over ``files``; sealed in the evaluator's store

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "root": str(self.root),
                "files": self.files, "digest": self.digest}

    @classmethod
    def from_dict(cls, d: dict) -> "Handoff":
        return cls(run_id=d["run_id"], root=Path(d["root"]),
                   files=d["files"], digest=d["digest"])


def _iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in _SKIP_NAMES for part in path.relative_to(root).parts):
            continue
        if path.is_file() and not path.is_symlink():
            yield path


def seal_handoff(*, run_id: str, source: Path, dest: Path, link: bool = True) -> Handoff:
    """Snapshot ``source`` into ``dest`` read-only and record what was handed over.

    ``link=True`` hard-links where the filesystem allows it, so a large run costs
    nothing to hand over; the snapshot files are then made read-only. A hard link
    shares an inode with the agent's live file, which is deliberate: an in-place
    edit by the agent is then visible to :func:`verify_handoff` rather than
    silently diverging. ``link=False`` copies instead, for a different filesystem.
    """
    source, dest = Path(source), Path(dest)
    if not source.is_dir():
        raise FileNotFoundError(f"handoff source {source} is not a directory")
    dest.mkdir(parents=True, exist_ok=True)

    files: dict = {}
    for path in _iter_files(source):
        rel = path.relative_to(source).as_posix()
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        linked = False
        if link:
            try:
                os.link(path, target)
                linked = True
            except OSError:
                linked = False
        if not linked:
            shutil.copy2(path, target)
        os.chmod(target, 0o444)
        files[rel] = {"sha256": _sha256(target), "size": target.stat().st_size}

    return Handoff(run_id=run_id, root=dest, files=files, digest=manifest_digest(files))


def verify_handoff(handoff: Handoff) -> None:
    """Re-hash the snapshot against the sealed manifest.

    Raises :class:`TamperDetected` naming the first path that moved, so an
    artefact edited after handoff is a named failure and not a quiet re-score.
    """
    root = Path(handoff.root)
    present = {p.relative_to(root).as_posix() for p in _iter_files(root)}
    expected = set(handoff.files)

    for rel in sorted(expected - present):
        raise TamperDetected("artefact_removed_after_handoff",
                             f"{rel} was in the handoff manifest and is gone")
    for rel in sorted(present - expected):
        raise TamperDetected("artefact_added_after_handoff",
                             f"{rel} appeared in the handoff after it was sealed")
    for rel in sorted(expected):
        got = _sha256(root / rel)
        want = handoff.files[rel]["sha256"]
        if got != want:
            raise TamperDetected(
                "artefact_edited_after_handoff",
                f"{rel} was {want} at handoff and is {got} now")

    if manifest_digest(handoff.files) != handoff.digest:
        raise TamperDetected("manifest_edited_after_handoff",
                             f"manifest digest {handoff.digest} does not cover its own files")
