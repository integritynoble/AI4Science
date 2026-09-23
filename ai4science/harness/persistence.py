from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from ai4science.harness.events import ImagePart, Message, ToolCall


def sessions_dir() -> Path:
    from ai4science import user
    base = user.config_path().parent / "sessions"
    base.mkdir(parents=True, exist_ok=True)
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
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


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
    returned with a dangling tool call: a trailing assistant message whose
    tool calls have no tool results would make the next request invalid, so
    it is dropped too (the turn is simply re-asked)."""
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
    while history:
        last = history[-1]
        if last.role == "assistant" and last.tool_calls:
            answered = {m.tool_call_id for m in history if m.role == "tool"}
            if all(tc.id in answered for tc in last.tool_calls):
                break
            history.pop()
            continue
        if last.role == "tool":
            # Tool results for a call that is (now) unanswered-for: find the
            # assistant message they belong to; if some of its calls have no
            # result, drop the whole group and re-check.
            i = len(history) - 1
            while i >= 0 and history[i].role == "tool":
                i -= 1
            if i < 0 or history[i].role != "assistant":
                history.pop()
                continue
            answered = {m.tool_call_id for m in history[i + 1:]}
            if all(tc.id in answered for tc in history[i].tool_calls):
                break
            del history[i:]
            continue
        break
    return history


def most_recent(workspace: Path) -> Optional[str]:
    return _read_index().get(str(workspace.resolve()))
