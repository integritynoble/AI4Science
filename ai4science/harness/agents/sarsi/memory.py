"""Validated memory — lessons written by triggers, read before acting.

A lesson written by choice does not test the trigger. This module exists
for the fixed triggers only:

  * `refuted_prediction` — a phase's `Verified when:` was checked and failed;
  * `rollback`           — a phase was cleared after it had been touched;
  * `refusal`            — the session refused, or the brief could not land;
  * `clash`              — the same action was taken twice against the
                           same target (exactly-once violated).

Each lesson is one file under `lessons/`; `MEMORY.md` is the one-line index
the session reads before it plans or resumes. The index is bounded the way
the workspace is bounded: the newest lesson wins, the overflow is counted,
and a quiet truncation is not allowed to read like completeness.

Nothing here is summarised by a model. A lesson is the trigger, the title,
and the detail the harness already had in hand at the moment the trigger
fired — promoted, not invented.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

TRIGGERS = ("refuted_prediction", "rollback", "refusal", "clash")

#: How many lessons the index may carry. A memory that grows without bound
#: stops being an index and becomes a second transcript.
MAX_INDEX_LINES = 20
#: A lesson title longer than this is a paragraph wearing a hat.
MAX_TITLE = 120
#: A lesson detail longer than this is a report, not a lesson.
MAX_DETAIL = 800


def memory_dir(config: Config, agent: Agent) -> Path:
    """Where this agent's memory lives: beside its tasks, under the vault."""
    return agent.tasks.parent / "memory"


def index_path(config: Config, agent: Agent) -> Path:
    return memory_dir(config, agent) / "MEMORY.md"


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "lesson"


def lesson_path(config: Config, agent: Agent, ts: float, trigger: str,
                title: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(ts))
    return memory_dir(config, agent) / "lessons" / f"{stamp}-{trigger}-{_slug(title)}.md"


def record(config: Config, agent: Agent, trigger: str, title: str,
           detail: str = "", *, now=time.time) -> Optional[Path]:
    """Write one lesson and prepend its line to the index.

    Returns the lesson path, or `None` when the trigger is not one of the
    fixed ones — a lesson written for any other reason is a note, and notes
    do not earn a place in the index.
    """
    if trigger not in TRIGGERS:
        return None
    ts = float(now())
    title = " ".join((title or trigger).split())[:MAX_TITLE]
    detail = " ".join((detail or "").split())[:MAX_DETAIL]

    base = memory_dir(config, agent)
    (base / "lessons").mkdir(parents=True, exist_ok=True)
    path = lesson_path(config, agent, ts, trigger, title)
    body = [f"# {title}", "", f"trigger: {trigger}",
            f"when: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}", ""]
    if detail:
        body += [detail, ""]
    path.write_text("\n".join(body))

    _prepend_index(config, agent, path, trigger, title)
    return path


def _prepend_index(config: Config, agent: Agent, path: Path, trigger: str,
                   title: str) -> None:
    base = memory_dir(config, agent)
    idx = index_path(config, agent)
    lines: List[str] = []
    if idx.exists():
        lines = [l for l in idx.read_text().splitlines() if l.strip()]
    # drop the old header, if any
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    # drop any stale line for this same lesson (record retried)
    rel = path.name
    lines = [l for l in lines if l.strip() != f"- [{title}]({rel})"]
    lines.insert(0, f"- [{title}]({rel}) — {trigger}")
    kept, overflow = lines[:MAX_INDEX_LINES], len(lines) - MAX_INDEX_LINES
    out = ["# MEMORY — lessons written by trigger", ""]
    out += kept
    if overflow > 0:
        out.append(f"…and {overflow} older lesson(s) in lessons/")
    idx.write_text("\n".join(out) + "\n")


def load_index(config: Config, agent: Agent) -> str:
    """The index as the session reads it. Empty string when there is none —
    a session must not be told it has a memory it does not have."""
    idx = index_path(config, agent)
    if not idx.exists():
        return ""
    text = idx.read_text().strip()
    if not text:
        return ""
    return ("LESSONS FROM THIS AGENT'S PAST TASKS (written by trigger — "
            "a refuted prediction, a rollback, a refusal, a clash). "
            "Read the ones that bear on what you are about to do, and do "
            "not repeat them:\n\n" + text)


def staleness(config: Config, agent: Agent, task) -> str:
    """What has changed on disk since the session last looked.

    A brief that tells a resumed session what was true an hour ago is a
    prediction, not a fact. This is the observation that replaces it: the
    working tree, right now.
    """
    cwd = (task.session or {}).get("cwd") or task.work_root
    if not cwd or not Path(cwd).is_dir():
        return ""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(cwd),
            capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    if not lines:
        return "Working tree: clean (git status, just now)."
    shown = lines[:10]
    extra = len(lines) - len(shown)
    text = "Working tree right now (git status, observed just now):\n" + \
           "\n".join("  " + l for l in shown)
    if extra > 0:
        text += f"\n  …and {extra} more"
    return text
