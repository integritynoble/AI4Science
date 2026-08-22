"""Where the work got to — durably, and honestly about what changed. [§M3.3]

A worker that is killed mid-plan and restarted has to answer one question:
**which phase do I pick up?** Getting it wrong in either direction is
expensive. Resume too early and verified work is redone; resume too late and a
phase nobody judged is treated as finished.

Three properties make the answer trustworthy:

  * **the write is atomic.** A checkpoint half-written by a process that died
    during the write is worse than no checkpoint: it is a confident record of a
    state that never existed. Written to a temporary file in the same directory
    and moved into place, which is atomic on POSIX.
  * **the plan is hashed, not just named.** `plan0` after the owner rewrote its
    criteria is a different plan wearing the same name. Resuming "phase 3" of a
    plan whose phase 3 is now something else is the silent version of doing the
    wrong work. So the hash covers the goal and the criteria, and a mismatch
    stops the resume rather than guessing which phases still correspond.
  * **each verified phase carries the evidence that verified it.** A checkpoint
    that records only `passed: [0, 1]` cannot be audited later — it repeats a
    claim without its grounds.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

SCHEMA_VERSION = 2

#: What a resume needs the owner to do before it can continue.
REBASE = "rebase-required"


def plan_hash(task: tsk.Task) -> str:
    """A stable digest of what this plan actually asks for.

    Goal plus the ordered criteria — the things a phase index means. The plan's
    *name* is not in it: a rename is not a change of work, and a rewrite under
    the same name is.
    """
    body = "\n".join([(task.goal or "").strip()]
                     + [(c or "").strip() for c in (task.criteria or [])])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Checkpoint:
    task_id: str
    plan_version: str = "plan0"
    plan_hash: str = ""
    current_phase: Optional[int] = None
    phases_verified: List[int] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    last_updated: str = ""
    schema_version: int = SCHEMA_VERSION

    def as_record(self) -> Dict[str, Any]:
        return {"schema_version": self.schema_version, "task_id": self.task_id,
                "plan_version": self.plan_version, "plan_hash": self.plan_hash,
                "current_phase": self.current_phase,
                "phases_verified": list(self.phases_verified),
                "evidence": dict(self.evidence),
                "last_updated": self.last_updated}


def path_for(agent: Agent, task_id: str):
    return tsk.dir_of(agent, task_id) / "checkpoint.json"


def write(config: Config, agent: Agent, task: tsk.Task) -> Checkpoint:
    """Record where this task stands. Atomic; never raises."""
    verified = [i for i in range(len(task.criteria or []))
                if tsk.phase_passed(task, i)]
    evidence: Dict[str, Any] = {}
    for i in verified:
        v = (task.phase_verdicts or {}).get(str(i)) or {}
        if isinstance(v, dict):
            evidence[str(i)] = {"state": v.get("state"), "why": (v.get("why") or "")[:300],
                                "engine": v.get("engine", ""),
                                "independent": v.get("independent"),
                                "verifier_sha": v.get("verifier_sha", "")}
    ck = Checkpoint(task_id=task.id,
                    plan_version=task.plan_version or "plan0",
                    plan_hash=plan_hash(task),
                    current_phase=tsk.earliest_incomplete(task),
                    phases_verified=verified,
                    evidence=evidence,
                    last_updated=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        p = path_for(agent, task.id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ck.as_record(), indent=2))
        os.replace(tmp, p)        # atomic: a reader sees the old file or the new
    except Exception:
        pass
    return ck


def read(agent: Agent, task_id: str) -> Optional[Checkpoint]:
    """The last checkpoint, or None. v1 rows (no hash) load with an empty hash."""
    try:
        raw = json.loads(path_for(agent, task_id).read_text())
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return Checkpoint(task_id=raw.get("task_id", task_id),
                      plan_version=raw.get("plan_version", "plan0"),
                      plan_hash=raw.get("plan_hash", ""),
                      current_phase=raw.get("current_phase"),
                      phases_verified=list(raw.get("phases_verified") or []),
                      evidence=dict(raw.get("evidence") or {}),
                      last_updated=raw.get("last_updated", ""),
                      schema_version=int(raw.get("schema_version", 1)))


@dataclass(frozen=True)
class Resume:
    """Where to pick up — or why it must not be picked up automatically."""
    phase: Optional[int] = None
    why: str = ""
    blocked: str = ""            #: REBASE when the plan changed under the record

    @property
    def ok(self) -> bool:
        return not self.blocked


def resume_point(config: Config, agent: Agent, task: tsk.Task) -> Resume:
    """The first unverified phase of a plan the checkpoint still describes.

    A changed plan hash stops here. The alternative — mapping old phase indexes
    onto new criteria — is a guess about which work still counts, and the one
    thing a restart must not do is invent its own place in a plan the owner has
    rewritten. [§M3.3]
    """
    ck = read(agent, task.id)
    live = plan_hash(task)
    if ck is None:
        first = tsk.earliest_incomplete(task)
        return Resume(phase=first,
                      why="no checkpoint — starting from the first incomplete "
                          "phase in the task store")
    if ck.plan_hash and ck.plan_hash != live:
        return Resume(phase=None, blocked=REBASE,
                      why=(f"the plan changed under this checkpoint "
                           f"({ck.plan_hash} → {live}): phase numbers no longer "
                           f"refer to the same work. Rebase or replan explicitly "
                           f"— resuming would pick a phase by its index alone."))
    if not ck.plan_hash:
        # A v1 checkpoint predates hashing. It is used, and said to be weaker:
        # unreadable provenance is not the same as wrong provenance.
        return Resume(phase=ck.current_phase,
                      why="checkpoint predates plan hashing — resuming on "
                          "phase index alone, which is weaker evidence")
    return Resume(phase=ck.current_phase,
                  why=f"first unverified phase of {ck.plan_version} "
                      f"({len(ck.phases_verified)} verified)")
