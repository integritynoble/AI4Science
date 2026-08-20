"""Export a finished sarsi task as a Markdown document — §12.

§12: "sarsi-worker should take down history and finished task. The
finished task can be put into md file or others in computer."

Open questions from the spec answered here:
  Q23 (where): task_dir/finished.md — beside the plan and record
  Q24 (when):  automatically on archive (the terminal state)

The file is also symlinked from <agent_dir>/finished/ so the owner
can find all exports in one place without knowing task IDs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def render(config, agent, task) -> str:
    """Render a finished task to a Markdown string."""
    from ai4science.harness.agents.sarsi import task as tsk, ledger

    lines = [
        f"# {task.name or task.id}",
        "",
        f"**Goal:** {task.goal}",
        f"**State:** {task.state}",
        f"**Agent:** {agent.id}",
        f"**Task ID:** {task.id}",
        "",
    ]

    # Plan
    plan = tsk.read_plan(config, agent, task)
    if plan:
        lines += ["## Plan", "", plan.render(), ""]

    # Final verdict
    if not task.verdict:
        # SILENCE IS NOT SUCCESS. Omitting the section entirely when no verdict
        # was recorded leaves a document that reads exactly like a task that
        # succeeded -- the reader cannot tell "finished well" from "finished
        # with nothing recorded". This fleet has been caught by that shape more
        # than once, which is why `spawn()` reports `unknown` as a real answer
        # rather than guessing. Say it instead.
        lines += ["## Final Verdict", "",
                  "**No verdict was recorded.** This task was archived without "
                  "one, so nothing here says it succeeded.", ""]
    if task.verdict:
        v = task.verdict
        st = str(v.get("state", "")).upper()
        reason = v.get("reason", "")
        lines += ["## Final Verdict", ""]
        lines.append(f"**{st}**" + (f" — {reason}" if reason else ""))
        for ev in (v.get("evidence") or [])[:10]:
            lines.append(f"- {ev}")
        lines.append("")

    # Per-phase verdicts
    pv = task.phase_verdicts or {}
    if pv:
        lines += ["## Phase Results", ""]
        for key in sorted(pv, key=lambda k: int(k) if str(k).isdigit() else 0):
            v = pv.get(key) or {}
            label = f"Phase {int(key) + 1}" if str(key).isdigit() else f"Phase {key}"
            st = str(v.get("state", "?")).upper()
            reason = str(v.get("reason", ""))[:200]
            lines.append(f"### {label}: {st}")
            if reason:
                lines.append(reason)
            lines.append("")

    # Event history from ledger
    rows = [r for r in ledger.read(config, "reports")
            if r.get("task") == task.id]
    if rows:
        lines += ["## History", ""]
        for r in rows[-20:]:
            ts = str(r.get("at", ""))[:19]
            st = r.get("state", "")
            ev = "; ".join(r.get("evidence") or [])[:100]
            lines.append(f"- `{ts}` {st}" + (f" — {ev}" if ev else ""))
        lines.append("")

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines += [f"---", f"*Exported {ts}*", ""]
    return "\n".join(lines)


def write(config, agent, task) -> Optional[Path]:
    """Write finished.md into the task directory. Returns path or None on error.

    Also creates a symlink in <agent_dir>/finished/ so all exports are
    reachable without knowing task IDs.
    """
    try:
        from ai4science.harness.agents.sarsi import task as tsk
        task_dir = tsk.dir_of(agent, task.id)
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / "finished.md"
        path.write_text(render(config, agent, task))

        # Index symlink: <agent_dir>/finished/<name-or-id>.md -> ../tasks/<id>/finished.md
        finished_dir = agent.agent_dir / "finished"
        finished_dir.mkdir(parents=True, exist_ok=True)
        slug = task.name or task.id
        link = finished_dir / f"{slug}.md"
        if not link.exists():
            try:
                link.symlink_to(path)
            except (OSError, NotImplementedError):
                pass   # symlinks unavailable — the file in task_dir is enough

        return path
    except Exception:
        return None
