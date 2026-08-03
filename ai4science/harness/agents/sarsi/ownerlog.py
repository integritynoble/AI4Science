"""What the owner said to one agent — one log, both doors.

Lives in that agent's `W_name`, so it is per agent name and never shared: what
you told `work` is not `abraham`'s to read.

`already_said` is deliberately an **exact** match. A fuzzy one would suppress a
genuinely different question that merely read similarly, and silently not asking
for something the agent needs is worse than asking twice.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from ai4science.harness.agents.sarsi.registry import Agent, Config

LOG_NAME = "ownerlog.jsonl"
DEFAULT_LIMIT = 50


def append(config: Config, agent: Agent, text: str, *, surface: str,
           now: Callable[[], float] = time.time) -> Dict[str, Any]:
    record = {"text": text, "surface": surface,
              "at": datetime.fromtimestamp(now(), timezone.utc).isoformat(timespec="seconds")}
    path = _path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return record


def said(config: Config, agent: Agent, limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """The most recent entries, oldest first. Bounded — the file is the history,
    this is a window over it."""
    path = _path(agent)
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out[-limit:] if limit else out


def already_said(config: Config, agent: Agent, text: str) -> bool:
    needle = (text or "").strip()
    return any((e.get("text") or "").strip() == needle
               for e in said(config, agent, limit=0))


def _path(agent: Agent) -> Path:
    return agent.workspace / LOG_NAME
