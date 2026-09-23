from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from .contract import TaskContract

@dataclass
class TaskState:
    task_id: str
    contract: TaskContract
    journal: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    checklist: list = field(default_factory=list)
    finished: bool = False
    final_status: str | None = None
    cursor: int = 0
    #: What resume() found in the log besides records: `torn_tails` are crash
    #: remnants a later append closed off (recoverable, expected);
    #: `unexplained_corruption` is an interior line nothing accounts for — an
    #: integrity failure, surfaced here and raised under strict resume.
    integrity: dict = field(default_factory=lambda: {"torn_tails": 0,
                                                     "unexplained_corruption": 0})


class StoreIntegrityError(RuntimeError):
    """An interior line of an append-only log is unreadable and no repair
    marker explains it. The recoverable history is still returned by a
    tolerant resume; strict callers refuse to build on it."""


class TaskStore:
    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self._root / f"{task_id}.jsonl"

    def open_or_resume(self, task_id: str, contract: TaskContract, *,
                       strict: bool = False) -> TaskState:
        existing = self.resume(task_id, strict=strict)
        if existing is not None:
            return existing
        state = TaskState(task_id=task_id, contract=contract)
        self._append(task_id, {"kind": "open", "contract": contract.to_dict()})
        return state

    def record(self, state: TaskState, *, kind: str, payload: dict) -> None:
        self._append(state.task_id, {"kind": kind, **payload})
        self._apply(state, kind, payload)

    def checkpoint(self, state: TaskState) -> None:
        self._append(state.task_id, {"kind": "checkpoint", "cursor": state.cursor})

    def resume(self, task_id: str, *, strict: bool = False) -> TaskState | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        state: TaskState | None = None
        torn, unexplained = 0, []
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # A crash mid-append leaves a torn trailing line; treat it as EOF
                # and return the recoverable prefix. An interior unreadable line
                # is one of two things: the remnant of such a crash that a later
                # _append closed off (it is followed by a `torn` marker — expected,
                # counted), or corruption nothing explains — counted separately
                # and, under strict resume, refused. Either way replay continues
                # so recoverable history is never lost.
                if i == len(lines) - 1:
                    torn += 1
                    break
                if _is_torn_marker(lines[i + 1]):
                    torn += 1
                else:
                    unexplained.append(i + 1)
                continue
            kind = rec.get("kind")
            if kind == "torn":
                continue                      # the marker itself carries no state
            if kind == "open":
                state = TaskState(task_id=task_id,
                                  contract=TaskContract.from_dict(rec["contract"]))
            elif state is not None and kind == "checkpoint":
                state.cursor = rec.get("cursor", state.cursor)
            elif state is not None:
                self._apply(state, kind, {k: v for k, v in rec.items() if k != "kind"})
        if state is not None:
            state.integrity = {"torn_tails": torn,
                               "unexplained_corruption": len(unexplained)}
        if unexplained and strict:
            raise StoreIntegrityError(
                f"{path.name}: unreadable interior line(s) {unexplained} with no "
                f"repair marker — not a crash remnant; refusing to build on it")
        return state

    def _apply(self, state: TaskState, kind: str, payload: dict) -> None:
        if kind == "step":
            state.journal.append(payload); state.cursor += 1
        elif kind == "assumption":
            state.assumptions.append(payload)
        elif kind == "artifact":
            state.artifacts.append(payload)
        elif kind == "checklist":
            state.checklist.append(payload)
        elif kind == "finish":
            state.finished = True
            state.final_status = payload.get("status")

    def _append(self, task_id: str, record: dict) -> None:
        path = self._path(task_id)
        # Close off any torn trailing line left by a crashed prior append, so the
        # new record lands on its own parseable line instead of being concatenated
        # onto the truncated remnant. The remnant then becomes an interior line;
        # the `torn` marker written right after it is how resume() tells that
        # expected remnant from corruption nothing explains. O(1): only the last
        # byte is inspected.
        if path.exists() and path.stat().st_size > 0:
            with path.open("rb") as f:
                f.seek(-1, 2)
                last_byte = f.read(1)
            if last_byte != b"\n":
                with path.open("a") as f:
                    f.write("\n" + json.dumps({"kind": "torn", "repaired": True}) + "\n")
        with path.open("a") as f:
            f.write(json.dumps(record) + "\n")


def _is_torn_marker(line: str) -> bool:
    try:
        return json.loads(line).get("kind") == "torn"
    except (ValueError, AttributeError):
        return False
