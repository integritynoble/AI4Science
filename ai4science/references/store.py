"""The reference-record store: one record, sealed by hash, appended to a file.

The seal exists for one reason. A reference is the thing an optimising agent is
measured against, so the agent has an interest in the reference moving. A record
whose output can be edited in place measures nothing: the next run would be
compared against whatever the last run made convenient. So the record carries a
SHA-256 over its own canonical body, and every read re-checks it.

What the seal does and does not buy, said plainly: it detects a changed record.
It does not *prevent* one. Anything that can rewrite the body can recompute the
seal, because the digest is not keyed — sealing it against the optimiser needs
either a key the agent cannot read or a store the agent cannot write, which is
the access-boundary half of Phase 5 and is not implemented here.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

#: Bumped when the sealed body's shape changes — a record sealed under an older
#: schema would otherwise fail verification for a reason that is not tampering.
SCHEMA = "reference-record/2"

#: The two tiers A01 names. "basic" and "strong" describe how much capability
#: was spent on the run, not how much trust the output has earned; trust is
#: `status` + `verified_by`.
TIERS = ("basic", "strong")

#: A record is a candidate until something outside the model has checked it.
STATUSES = ("candidate", "reference")


class SealBroken(Exception):
    """The record's body does not hash to its seal."""


class RecordInvalid(ValueError):
    """The record is missing something a record must have."""


def _canonical(body: Dict[str, Any]) -> bytes:
    """Bytes that hash the same for two records that mean the same thing."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class CallCost:
    """What one model call cost. Every field is measured or is None.

    `usd_metered` is the provider's own number for this call (`total_cost_usd`
    from `claude -p --output-format json`). `usd_recomputed` is this repo's
    cache-aware price for the same token counts, kept beside it rather than
    instead of it: when they disagree the disagreement is the finding, and a
    reference whose cost was estimated should be able to say so.
    """
    usd_metered: Optional[float]
    usd_recomputed: Optional[float]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    wall_seconds: Optional[float] = None
    #: Every model the provider says served this ONE call, with its own metered
    #: cost. `claude -p --model claude-opus-5` bills two models: Opus answers and
    #: Haiku runs a side call. A record claiming the whole `total_cost_usd` was
    #: one model's would be wrong about what it paid for, so the composition is
    #: kept rather than collapsed. The token counts above are the ANSWERING
    #: model's.
    per_model_usd: Dict[str, float] = field(default_factory=dict)
    #: What could not be measured, named. Empty means everything above is real.
    not_measured: Sequence[str] = ()

    @property
    def usd(self) -> Optional[float]:
        """The number to spend against a budget: metered if the provider gave
        one, else the recomputation, else None — never silently zero."""
        if self.usd_metered is not None:
            return self.usd_metered
        return self.usd_recomputed


@dataclass(frozen=True)
class ReferenceRecord:
    """One run of one named model revision against one frozen task."""
    record_id: str
    tier: str                      # basic | strong
    task_id: str
    task_digest: str               # hash of the frozen task, so a moved task shows
    model_revision: str            # the exact string the provider reported
    model_requested: str           # the string asked for, which may be an alias
    output: str
    calls: Sequence[CallCost]
    recorded_at: str               # UTC ISO-8601
    status: str = "candidate"
    verified_by: Optional[str] = None
    grade: Optional[Dict[str, Any]] = None
    notes: Dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA
    seal: Optional[str] = None

    # -- validity ---------------------------------------------------------
    def validated(self) -> "ReferenceRecord":
        """Raise unless this record is one a store may hold."""
        if not (self.model_revision or "").strip():
            raise RecordInvalid(
                "a reference record needs the exact model revision it ran: "
                "a record that cannot name its model cannot be reproduced, "
                "and comparing a later run against it would compare two "
                "unknowns")
        if self.tier not in TIERS:
            raise RecordInvalid("tier must be one of %s, got %r"
                                % (", ".join(TIERS), self.tier))
        if self.status not in STATUSES:
            raise RecordInvalid("status must be one of %s, got %r"
                                % (", ".join(STATUSES), self.status))
        if self.status == "reference" and not (self.verified_by or "").strip():
            raise RecordInvalid(
                "a record may only be status='reference' if it names what "
                "checked it (verified_by); a model's own output is a candidate")
        if not self.calls:
            raise RecordInvalid("a reference record needs at least one call's cost")
        return self

    # -- cost -------------------------------------------------------------
    @property
    def cost_usd(self) -> Optional[float]:
        """Summed cost of every call, or None if no call could be priced."""
        priced = [c.usd for c in self.calls if c.usd is not None]
        return round(sum(priced), 6) if priced else None

    @property
    def cost_not_measured(self) -> List[str]:
        out: List[str] = []
        for i, c in enumerate(self.calls):
            out.extend("call %d: %s" % (i, m) for m in c.not_measured)
        return out

    # -- sealing ----------------------------------------------------------
    def body(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("seal", None)
        return d

    def sealed(self) -> "ReferenceRecord":
        self.validated()
        return replace(self, seal=seal_of(self))

    def check_seal(self) -> "ReferenceRecord":
        if not self.seal:
            raise SealBroken("record %s carries no seal" % self.record_id)
        actual = seal_of(self)
        if actual != self.seal:
            raise SealBroken(
                "record %s does not match its seal: sealed %s, body hashes to "
                "%s — the record was changed after it was recorded"
                % (self.record_id, self.seal[:12], actual[:12]))
        return self

    # -- promotion --------------------------------------------------------
    def promote(self, verified_by: str, grade: Optional[Dict[str, Any]] = None
                ) -> "ReferenceRecord":
        """Candidate → reference, naming what checked it.

        Promotion writes a NEW record rather than editing this one: the sealed
        candidate stays on the file, so the promotion is auditable against what
        the model actually produced.
        """
        if not (verified_by or "").strip():
            raise RecordInvalid("promotion must name what checked the output")
        return replace(self, status="reference", verified_by=verified_by,
                       grade=grade if grade is not None else self.grade,
                       record_id=self.record_id + "+verified",
                       seal=None).sealed()

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReferenceRecord":
        d = dict(d)
        d["calls"] = [CallCost(**{**c,
                                  "per_model_usd": dict(c.get("per_model_usd") or {}),
                                  "not_measured": tuple(c.get("not_measured") or ())})
                      for c in d.get("calls") or []]
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


def seal_of(record: ReferenceRecord) -> str:
    """SHA-256 over the record's canonical body, seal excluded."""
    return hashlib.sha256(_canonical(record.body())).hexdigest()


class ReferenceStore:
    """Append-only JSONL of sealed records.

    Append-only on purpose: `put` refuses to replace a record_id that is already
    on the file. A store that allows replacement allows the reference to move,
    and then nothing has been established.
    """

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    # -- write ------------------------------------------------------------
    def put(self, record: ReferenceRecord) -> ReferenceRecord:
        record = record.sealed() if record.seal is None else record.check_seal()
        if any(r.record_id == record.record_id for r in self._read_raw()):
            raise RecordInvalid(
                "record_id %r is already in %s; the store is append-only so a "
                "reference cannot be replaced in place"
                % (record.record_id, self.path))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), sort_keys=True,
                                ensure_ascii=False) + "\n")
        return record

    # -- read -------------------------------------------------------------
    def _read_raw(self) -> List[ReferenceRecord]:
        if not self.path.exists():
            return []
        out: List[ReferenceRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(ReferenceRecord.from_dict(json.loads(line)))
        return out

    def all(self) -> List[ReferenceRecord]:
        """Every record, each with its seal re-checked. Raises on a broken one:
        a store that returns a tampered record beside good ones invites a caller
        to use it."""
        return [r.check_seal() for r in self._read_raw()]

    def __iter__(self) -> Iterator[ReferenceRecord]:
        return iter(self.all())

    def broken(self) -> List[str]:
        """record_ids whose seal does not verify — for a tamper check that wants
        to report rather than raise."""
        out = []
        for r in self._read_raw():
            try:
                r.check_seal()
            except SealBroken:
                out.append(r.record_id)
        return out

    def get(self, record_id: str) -> ReferenceRecord:
        for r in self._read_raw():
            if r.record_id == record_id:
                return r.check_seal()
        raise KeyError(record_id)

    def tier(self, tier: str, task_id: Optional[str] = None
             ) -> List[ReferenceRecord]:
        return [r for r in self.all()
                if r.tier == tier and (task_id is None or r.task_id == task_id)]

    # -- cost -------------------------------------------------------------
    def total_cost_usd(self) -> float:
        """Every call in the store, summed. Calls that could not be priced are
        excluded from the sum and listed by `cost_not_measured`."""
        return round(sum(r.cost_usd or 0.0 for r in self.all()), 6)

    def cost_not_measured(self) -> List[str]:
        out: List[str] = []
        for r in self.all():
            out.extend("%s %s" % (r.record_id, m) for m in r.cost_not_measured)
        return out
