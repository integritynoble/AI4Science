"""Evidence-grounded self model — what the harness can truthfully observe.

Each field carries measured_at, evidence_ref, and stale_after_secs.
Staleness is computed at read time: a field not re-observed within its window
is `stale=True`. A stale field is reported as stale, not silenced.

Write rule: fields are written only by harness events — registry load, ledger
reads, task transitions, session completions. LLM self-report never writes here.
A field not yet measured is None, not 0 or "unknown" — silence is not success
(paper §3.4).

File: <agent_dir>/self_state.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _path(agent_dir: Path) -> Path:
    return agent_dir / "self_state.json"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age_secs(measured_at: Optional[str]) -> Optional[float]:
    """Seconds since measured_at, or None when not measured."""
    if not measured_at:
        return None
    try:
        from datetime import datetime, timezone
        t = datetime.fromisoformat(measured_at)
        return (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return None


def _load(agent_dir: Path) -> Dict[str, Any]:
    p = _path(agent_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save(agent_dir: Path, state: Dict[str, Any]) -> None:
    p = _path(agent_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def update(agent_dir: Path, field: str, value: Any,
           evidence_ref: str = "", stale_after_secs: int = 3600) -> None:
    """Write one field to the self model. Never raises."""
    try:
        state = _load(agent_dir)
        state[field] = {
            "value": value,
            "measured_at": _now_iso(),
            "evidence_ref": (evidence_ref or "").strip(),
            "stale_after_secs": int(stale_after_secs),
        }
        _save(agent_dir, state)
    except Exception:
        pass


def read(agent_dir: Path) -> Dict[str, Any]:
    """All fields with `stale` computed from age vs stale_after_secs."""
    state = _load(agent_dir)
    out: Dict[str, Any] = {}
    for name, rec in state.items():
        if not isinstance(rec, dict):
            continue
        age = _age_secs(rec.get("measured_at"))
        limit = rec.get("stale_after_secs", 3600)
        stale = (age is None) or (age > limit)
        out[name] = dict(rec, stale=stale, age_secs=round(age) if age is not None else None)
    return out


def is_stale(agent_dir: Path, field: str) -> bool:
    """Is this field stale (or unmeasured)?"""
    f = read(agent_dir).get(field)
    if f is None:
        return True
    return bool(f.get("stale", True))


def sync(config, agent) -> Dict[str, Any]:
    """Populate observable fields from harness state. Returns the current read."""
    d = agent.agent_dir

    # identity — static; stale_after = 30 days
    try:
        update(d, "identity", {
            "agent_id": agent.id,
            "role": agent.role,
            "owner_id": config.owner_id,
        }, evidence_ref="registry:sarsi.json", stale_after_secs=86400 * 30)
    except Exception:
        pass

    # authority — from registry + trust ledger; stale_after = 1 hour
    try:
        from ai4science.harness.agents.sarsi import selfaware as _sa
        eff, why = _sa._effective(agent.ceiling)
        update(d, "authority", {
            "configured": agent.ceiling,
            "effective": eff,
            "why": why,
        }, evidence_ref="trust-ledger", stale_after_secs=3600)
    except Exception:
        pass

    # active_intention — from task store; stale_after = 5 min
    try:
        from ai4science.harness.agents.sarsi import task as tsk, entry as _entry
        rows = tsk.all_of(config, agent)
        standing_id = None
        try:
            standing_id = _entry.current(config, agent)
        except Exception:
            pass
        update(d, "active_intention", {
            "task_count": len(rows),
            "standing_task_id": standing_id,
        }, evidence_ref="task-store", stale_after_secs=300)
    except Exception:
        pass

    # executor — last session completion; stale_after = 24h (written by session.py)
    # Not synced here — session.py writes this on session completion.

    return read(d)


def render(agent_dir: Path) -> str:
    """Non-stale self-model fields formatted for context injection.

    Stale fields are still mentioned so the LLM knows they exist but are
    unverified — silence about a stale authority field is worse than reporting
    it stale.
    """
    state = read(agent_dir)
    if not state:
        return ""
    lines = ["self model (harness-observed):"]
    for name in ("identity", "authority", "active_intention", "executor"):
        rec = state.get(name)
        if rec is None:
            lines.append(f"  {name}: not yet measured")
            continue
        val = rec.get("value")
        stale = rec.get("stale", True)
        age = rec.get("age_secs")
        age_str = f" (age {age}s)" if age is not None else ""
        stale_str = " [STALE]" if stale else ""
        lines.append(f"  {name}{stale_str}{age_str}: {json.dumps(val)}")
    return "\n".join(lines)


def readiness(config, agent, task=None) -> Tuple[bool, List[str]]:
    """Is the agent in a state where assigning a session is safe?

    Returns (ready, gaps) where gaps is a list of human-readable problems.
    A gap means a required field is stale or null. Soft check — the caller
    decides whether to block or warn.
    """
    gaps: List[str] = []
    d = agent.agent_dir

    if is_stale(d, "authority"):
        gaps.append("authority field is stale or unmeasured — "
                    "ceiling may have changed since last check")

    if task is not None:
        try:
            from ai4science.harness.agents.sarsi import task as tsk
            plan = tsk.read_plan(config, agent, task)
            if plan is None:
                gaps.append(f"task {task.id} has no plan — cannot assign session "
                            "without an agreed plan")
        except Exception:
            pass
        if task.awaiting:
            gaps.append(f"task {task.id} is still awaiting grants: "
                        + ", ".join(task.awaiting))

    return len(gaps) == 0, gaps
