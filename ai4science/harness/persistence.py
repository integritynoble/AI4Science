from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from ai4science.harness.events import Message, ToolCall


def sessions_dir() -> Path:
    from ai4science import user
    base = user.config_path().parent / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _to_record(m: Message) -> dict:
    return {
        "role": m.role,
        "content": m.content,
        "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                       for tc in m.tool_calls],
        "tool_call_id": m.tool_call_id,
    }


def _from_record(d: dict) -> Message:
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        tool_calls=[ToolCall(t["id"], t["name"], t["arguments"])
                    for t in d.get("tool_calls", [])],
        tool_call_id=d.get("tool_call_id"),
    )


def _index_path() -> Path:
    return sessions_dir() / "index.json"


def save(session_id: str, workspace: Path, history: List[Message]) -> None:
    path = sessions_dir() / f"{session_id}.jsonl"
    with path.open("w") as f:
        for m in history:
            f.write(json.dumps(_to_record(m)) + "\n")
    idx = {}
    if _index_path().exists():
        idx = json.loads(_index_path().read_text())
    idx[str(workspace.resolve())] = session_id
    _index_path().write_text(json.dumps(idx))


def load(session_id: str) -> List[Message]:
    path = sessions_dir() / f"{session_id}.jsonl"
    if not path.exists():
        return []
    return [_from_record(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def most_recent(workspace: Path) -> Optional[str]:
    if not _index_path().exists():
        return None
    idx = json.loads(_index_path().read_text())
    return idx.get(str(workspace.resolve()))
