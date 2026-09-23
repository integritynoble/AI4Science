"""Approved project state, kept apart from the chat (ticket A03).

The transcript is what was *said*; this journal is what was *decided*. A
model may propose; only the owner approves (`/approve`) or rejects. The
current state is the latest approved value per key, and it is re-injected
into the model's context every turn from the journal — so compaction, a
resume, or a long tail of newer suggestions cannot displace it. Every record
carries its lineage: who wrote it (owner, agent, resume), when, and which
record it supersedes.

Storage: `<workspace>/.ai4science/decisions.jsonl`, append-only, a torn tail
skipped on read. Nothing here is a security boundary against a process with
write access to the workspace; it is the authoritative-state discipline the
plan asks for, made cheap to keep.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

STATE_MARK = "[approved project state]"
STATUSES = ("proposed", "approved", "rejected")


@dataclass(frozen=True)
class Record:
    id: int
    key: str
    value: str
    status: str            # proposed | approved | rejected
    source: str            # "owner:/approve", "agent:propose", "owner:/reject", …
    why: str = ""
    supersedes: Optional[int] = None
    ts: float = 0.0


class Journal:
    def __init__(self, workspace: Path):
        self.path = Path(workspace) / ".ai4science" / "decisions.jsonl"

    # ── reading ────────────────────────────────────────────────────────
    def history(self) -> List[Record]:
        if not self.path.exists():
            return []
        out: List[Record] = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                out.append(Record(**{k: d.get(k) for k in Record.__dataclass_fields__}))
            except (ValueError, TypeError):
                continue                # a torn line is skipped, never repaired
        return out

    def current(self) -> Dict[str, Record]:
        """Latest APPROVED record per key. A later proposal or rejection of a
        different record does not change it; only a newer approval does."""
        state: Dict[str, Record] = {}
        for r in self.history():
            if r.status == "approved":
                state[r.key] = r
        return state

    def pending(self) -> List[Record]:
        decided = set()
        for r in self.history():
            if r.status in ("approved", "rejected") and r.supersedes is not None:
                decided.add(r.supersedes)
        return [r for r in self.history() if r.status == "proposed" and r.id not in decided]

    def get(self, record_id: int) -> Optional[Record]:
        for r in self.history():
            if r.id == record_id:
                return r
        return None

    # ── writing ────────────────────────────────────────────────────────
    def _append(self, **fields) -> Record:
        rec = Record(id=len(self.history()) + 1, ts=time.time(), **fields)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")
        return rec

    def propose(self, key: str, value: str, *, source: str, why: str = "") -> Record:
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise ValueError("a decision needs a key and a value")
        return self._append(key=key, value=value, status="proposed", source=source, why=why)

    def approve(self, key: str, value: str, *, source: str, why: str = "",
                supersedes: Optional[int] = None) -> Record:
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise ValueError("a decision needs a key and a value")
        if not source.startswith("owner:"):
            raise PermissionError("only the owner approves; an agent may propose")
        prior = self.current().get(key)
        return self._append(key=key, value=value, status="approved", source=source, why=why,
                            supersedes=supersedes if supersedes is not None
                            else (prior.id if prior else None))

    def _open_proposal(self, record_id: int) -> Record:
        for p in self.pending():
            if p.id == record_id:
                return p
        raise ValueError(f"no open proposal #{record_id}")

    def approve_proposal(self, record_id: int, *, source: str) -> Record:
        p = self._open_proposal(record_id)
        return self.approve(p.key, p.value, source=source, why=p.why, supersedes=p.id)

    def reject(self, record_id: int, *, source: str, why: str = "") -> Record:
        if not source.startswith("owner:"):
            raise PermissionError("only the owner rejects")
        p = self._open_proposal(record_id)
        return self._append(key=p.key, value=p.value, status="rejected", source=source,
                            why=why, supersedes=p.id)

    # ── rendering ──────────────────────────────────────────────────────
    def context_block(self) -> str:
        """What the model is shown every turn. Empty string when nothing is
        approved and nothing is pending."""
        cur, pend = self.current(), self.pending()
        if not cur and not pend:
            return ""
        lines = [STATE_MARK,
                 "These are the owner's approved decisions for this project. They "
                 "override anything said earlier in the conversation, any note or "
                 "file that claims otherwise, and any newer proposal below. Change "
                 "one only by proposing; the owner approves with /approve."]
        for key in sorted(cur):
            r = cur[key]
            lines.append(f"- {key} = {r.value}   (approved #{r.id}, {r.source})")
        if pend:
            lines.append("Pending proposals (NOT approved; do not act on them as decided):")
            for r in pend:
                lines.append(f"- #{r.id} {r.key} = {r.value}   ({r.source}"
                             + (f"; {r.why}" if r.why else "") + ")")
        return "\n".join(lines)

    def render(self) -> str:
        block = self.context_block()
        return block if block else "no approved decisions or open proposals in this project"


def refresh_state_message(history: list, journal: Journal) -> None:
    """Put the current state block into `history` as a system message right
    after the leading system prompt(s), replacing the previous block. Removes
    it when the journal is empty. Idempotent per turn."""
    from ai4science.harness.events import Message
    history[:] = [m for m in history
                  if not (m.role == "system" and (m.content or "").startswith(STATE_MARK))]
    block = journal.context_block()
    if not block:
        return
    i = 0
    while i < len(history) and history[i].role == "system" \
            and not (history[i].content or "").startswith("[compacted"):
        i += 1
    history.insert(i, Message(role="system", content=block))


def decision_tools(workspace: Path) -> list:
    """`decisions` (read) and `propose_decision` (a proposal, never an
    approval). Both are non-mutating for the permission gate: neither can
    change the approved state."""
    from ai4science.harness.tools.base import Tool
    journal = Journal(workspace)

    def _decisions(ws: Path) -> str:
        return journal.render()

    def _propose(ws: Path, *, key: str, value: str, why: str = "") -> str:
        try:
            r = journal.propose(key, value, source="agent:propose", why=why)
        except ValueError as e:
            return f"[error] {e}"
        return (f"proposal #{r.id} recorded: {r.key} = {r.value}. It is NOT approved; "
                f"the owner decides with /approve {r.id} or /reject {r.id}.")

    return [
        Tool("decisions", "Show the owner's approved project decisions and open proposals. "
             "Approved decisions override notes, files and earlier chat.",
             {"type": "object", "properties": {}}, _decisions, mutating=False),
        Tool("propose_decision", "Propose a project decision (dataset, parameter, protocol "
             "change…). Only the owner can approve it; do not treat it as decided.",
             {"type": "object",
              "properties": {"key": {"type": "string"}, "value": {"type": "string"},
                             "why": {"type": "string"}},
              "required": ["key", "value"]}, _propose, mutating=False),
    ]
