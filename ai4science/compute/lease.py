"""Filesystem counting-semaphore so a compute provider serves a bounded number
of users at once.

The requirement: the main CPU server and the sub-GPU server each serve at most
two users concurrently; a third user waits. Dispatch is cross-machine over the
shared file-inbox (see dispatch.py), so the lease lives in the same shared
``endpoint_path`` directory both the dispatcher and the provider can see.

Each provider exposes ``max_concurrent`` slots. A slot is a single file
``lease_slot_<i>.json`` created with O_EXCL — the OS guarantees only one writer
wins the create, so acquiring a slot is atomic even if several dispatchers race.
A lease carries a TTL; an expired slot (holder crashed without releasing) is
reclaimed by the next acquirer so a slot is never wedged forever.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_TTL_S = 3600


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts)


class Lease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    slot: int
    holder: str                     # session id / wallet / job id holding the slot
    acquired_at: str = Field(default_factory=lambda: _utcnow().isoformat(timespec="seconds"))
    ttl_s: int = DEFAULT_TTL_S
    job_id: str = ""

    def is_expired(self, now: Optional[dt.datetime] = None) -> bool:
        now = now or _utcnow()
        try:
            return _parse(self.acquired_at) + dt.timedelta(seconds=self.ttl_s) < now
        except ValueError:
            return True  # unparseable timestamp → treat as stale


def _endpoint(provider) -> Path:
    p = Path(provider.endpoint_path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _slot_path(provider, i: int) -> Path:
    return _endpoint(provider) / f"lease_slot_{i}.json"


def _read_slot(path: Path) -> Optional[Lease]:
    try:
        return Lease.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def active_leases(provider) -> List[Lease]:
    """Non-expired leases currently held on this provider."""
    out: List[Lease] = []
    now = _utcnow()
    for i in range(int(provider.max_concurrent)):
        lease = _read_slot(_slot_path(provider, i))
        if lease is not None and not lease.is_expired(now):
            out.append(lease)
    return out


def available_slots(provider) -> int:
    return max(0, int(provider.max_concurrent) - len(active_leases(provider)))


def _write_slot(path: Path, lease: Lease) -> bool:
    """Atomically create the slot file (O_EXCL). False if already held."""
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        os.write(fd, (lease.model_dump_json(indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return True


def acquire_lease(provider, *, holder: str, ttl_s: int = DEFAULT_TTL_S,
                  job_id: str = "") -> Optional[Lease]:
    """Claim a free slot. Returns the Lease, or None if the server is full.

    Atomic per slot via O_EXCL. An expired slot is reclaimed: its stale file is
    removed and the slot is re-attempted.
    """
    n = int(provider.max_concurrent)
    for i in range(n):
        path = _slot_path(provider, i)
        lease = Lease(provider_id=provider.provider_id, slot=i, holder=holder,
                      ttl_s=ttl_s, job_id=job_id)
        if _write_slot(path, lease):
            return lease
        # Slot file exists — reclaim it if the current holder's lease expired.
        existing = _read_slot(path)
        if existing is not None and existing.is_expired():
            try:
                path.unlink()
            except OSError:
                continue
            if _write_slot(path, lease):
                return lease
    return None


def release_lease(provider, lease: Lease) -> bool:
    """Release a slot. Only the recorded holder may release it (returns False
    otherwise, so a forged lease can't free someone else's slot)."""
    path = _slot_path(provider, lease.slot)
    existing = _read_slot(path)
    if existing is None:
        return False
    if existing.holder != lease.holder:
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False
