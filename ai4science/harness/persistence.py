from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from ai4science.harness.events import ImagePart, Message, ToolCall


def sessions_dir() -> Path:
    from ai4science import user
    base = user.config_path().parent / "sessions"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    base.chmod(0o700)
    return base


def _to_record(m: Message) -> dict:
    return {
        "role": m.role,
        "content": m.content,
        "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments,
                        "extra": tc.extra}
                       for tc in m.tool_calls],
        "tool_call_id": m.tool_call_id,
        "images": [{"media_type": im.media_type, "data_b64": im.data_b64}
                   for im in m.images],
    }


def _from_record(d: dict) -> Message:
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        tool_calls=[ToolCall(t["id"], t["name"], t["arguments"], extra=t.get("extra"))
                    for t in d.get("tool_calls", [])],
        tool_call_id=d.get("tool_call_id"),
        images=[ImagePart(im["media_type"], im["data_b64"])
                for im in d.get("images", [])],
    )


def _index_path() -> Path:
    return sessions_dir() / "index.json"


def _atomic_write(path: Path, text: str) -> None:
    """Write via a sibling temp file and rename, so a kill mid-write leaves the
    previous file intact rather than a truncated one. The rename is atomic on
    POSIX; the temp file is fsynced first so the rename never points at
    unflushed bytes."""
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _sync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    # Windows does not expose a directory fsync through os.open. POSIX saves
    # include the rename in the durability guarantee; any failure propagates.
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def save(session_id: str, workspace: Path, history: List[Message]) -> None:
    """Persist the whole history. Called after every tool result and every
    turn, so a session killed mid-turn resumes at its last tool call rather
    than at its last completed turn. Atomic: see _atomic_write."""
    path = sessions_dir() / f"{session_id}.jsonl"
    _atomic_write(path, "".join(json.dumps(_to_record(m)) + "\n" for m in history))
    idx = _read_index()
    idx[str(workspace.resolve())] = session_id
    _atomic_write(_index_path(), json.dumps(idx))


def _read_index() -> dict:
    p = _index_path()
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except (ValueError, OSError):
        return {}          # an unreadable index loses the map, never the sessions


def load(session_id: str) -> List[Message]:
    """The saved history. A line that does not parse — a torn tail from a
    pre-atomic save, or a damaged file — is skipped, and a history is never
    returned with a dangling tool call: missing results are explicitly marked
    unresolved, preserving completed actions and preventing blind replays."""
    path = sessions_dir() / f"{session_id}.jsonl"
    if not path.exists():
        return []
    out: List[Message] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(_from_record(json.loads(line)))
        except (ValueError, KeyError, TypeError):
            continue
    return _without_dangling_tool_calls(out)


def _without_dangling_tool_calls(history: List[Message]) -> List[Message]:
    out = []
    i = 0
    while i < len(history):
        msg = history[i]
        if msg.role == "tool":
            i += 1  # orphan result from an unreadable assistant record
            continue
        out.append(msg)
        i += 1
        if msg.role != "assistant" or not msg.tool_calls:
            continue
        results = []
        while i < len(history) and history[i].role == "tool":
            results.append(history[i])
            i += 1
        answered = {m.tool_call_id for m in results}
        out.extend(results)
        for tc in msg.tool_calls:
            if tc.id not in answered:
                out.append(Message(role="tool", tool_call_id=tc.id, content=(
                    "[unresolved after recovery] No durable result for this call. "
                    "It may already have executed. Reconcile its effects with the "
                    "owner before repeating it; do not assume it failed.")))
    return out


def most_recent(workspace: Path) -> Optional[str]:
    return _read_index().get(str(workspace.resolve()))
