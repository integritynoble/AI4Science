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
    cursor: int = 0

class TaskStore:
    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self._root / f"{task_id}.jsonl"

    def open_or_resume(self, task_id: str, contract: TaskContract) -> TaskState:
        existing = self.resume(task_id)
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

    def resume(self, task_id: str) -> TaskState | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        state: TaskState | None = None
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            kind = rec.get("kind")
            if kind == "open":
                state = TaskState(task_id=task_id,
                                  contract=TaskContract.from_dict(rec["contract"]))
            elif state is not None and kind == "checkpoint":
                state.cursor = rec.get("cursor", state.cursor)
            elif state is not None:
                self._apply(state, kind, {k: v for k, v in rec.items() if k != "kind"})
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

    def _append(self, task_id: str, record: dict) -> None:
        with self._path(task_id).open("a") as f:
            f.write(json.dumps(record) + "\n")
