"""`SPD` — what a task actually cost.

One live task burned about eight minutes of unattended waiting and nothing
recorded it. Without this, "is this agent worth running?" is answered from
memory.

The numbers are **read, not estimated**. Claude Code writes a transcript per
working directory, each sarsi session has its own directory, and every turn in
that transcript carries a `usage` block. So the token counts here are the ones
the model reported, attributed per task by construction.

The shape of the *not*-knowing matters more than the numbers:

  * **unknown is not zero.** A transcript that cannot be read gives `None` and
    the report says so. Printing `0 tokens` for a session that ran for an hour
    is the most confident kind of wrong, and a total that quietly treats it as
    nothing understates every figure built on top of it.
  * **cached input is counted apart from fresh input.** Both are "input" and
    they are nowhere near the same cost; summing them makes a cheap session look
    expensive and hides the thing worth knowing.
  * **PWM is reported as "not charged here", never as 0.** These sessions run
    Claude Code, which this system does not meter — and `0 PWM` reads as free.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config


@dataclass
class Spend:
    """What one task, or one agent, cost. `None` means *not recorded*."""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    #: read from the prompt cache — far cheaper than fresh input, so kept apart
    cached_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    wall_seconds: Optional[float] = None
    still_running: bool = False
    #: how many tasks contributed no measurement at all
    unmeasured: int = 0
    tasks: int = 0
    agent_id: str = ""
    note: str = ""

    @property
    def measured(self) -> bool:
        return self.input_tokens is not None or self.output_tokens is not None

    @property
    def summary(self) -> str:
        parts: List[str] = []
        if self.note:
            parts.append(self.note)
        if self.measured:
            parts.append(f"{_n(self.input_tokens)} in / "
                         f"{_n(self.output_tokens)} out")
            if self.cached_tokens:
                parts.append(f"{_n(self.cached_tokens)} cached "
                             f"(+{_n(self.cache_write_tokens)} written)")
        else:
            parts.append("tokens: not recorded")
        if self.wall_seconds is not None:
            parts.append(_duration(self.wall_seconds) +
                         (" so far" if self.still_running else ""))
        if self.unmeasured:
            parts.append(f"{self.unmeasured} task(s) could not be measured")
        # never "0 PWM": these sessions are Claude Code, which this system does
        # not meter, and a zero reads as free
        parts.append("PWM: not charged here (Claude Code sessions)")
        return " · ".join(parts)


def _n(value: Optional[int]) -> str:
    return "—" if value is None else f"{value:,}"


def _duration(seconds: float) -> str:
    s = int(seconds)
    if s < 90:
        return f"{s}s"
    if s < 5400:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


# ── reading the transcript ────────────────────────────────────────────

def usage_of(cwd: str) -> List[Dict[str, Any]]:
    """Every `usage` block in this working directory's Claude Code transcript.

    Raises rather than returning `[]` when the transcript cannot be found or
    read — the caller distinguishes "nothing was spent" from "nothing could be
    read", and swallowing that here would erase the difference.
    """
    from ai4science.harness.agents.machine import sessions

    path = sessions._transcript_path(str(cwd))
    if not path:
        raise FileNotFoundError(f"no Claude Code transcript for {cwd}")
    # EVERY transcript in that project directory, not just the newest: each
    # `claude` launch writes a new one, so a task that was stopped and resumed
    # has several, and taking the newest would drop every earlier run's cost.
    out: List[Dict[str, Any]] = []
    for file in sorted(Path(path).parent.glob("*.jsonl")):
        try:
            handle = open(file, errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                usage = ((entry.get("message") or {}).get("usage")) or {}
                if usage:
                    out.append(usage)
    return out


# ── one task ──────────────────────────────────────────────────────────

def sessions_of(task: tsk.Task) -> List[Dict[str, Any]]:
    """Every session this task has had — the live one and the ended ones —
    with **one entry per working directory**.

    They share the task's folder, so they share a transcript directory; reading
    it once per session would double the cost of every restarted task.
    """
    out: List[Dict[str, Any]] = []
    seen = set()
    for record in list(task.past_sessions or []) + [task.session or {}]:
        cwd = (record or {}).get("cwd")
        if not cwd or cwd in seen:
            continue
        seen.add(cwd)
        out.append(record)
    return out


def for_task(config: Config, agent: Agent, task: tsk.Task, *,
             usage: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
             now=time.time) -> Spend:
    out = Spend(agent_id=agent.id, tasks=1)
    records = sessions_of(task)
    if not records:
        out.note = "not started — no session, so nothing was spent on one"
        out.unmeasured = 1
        return out
    session = task.session or records[-1]
    cwd = session.get("cwd")

    started = session.get("started_at")
    if started:
        end = now() if task.state not in _ENDED else _ended_at(task, now)
        out.wall_seconds = max(0.0, float(end) - float(started))
        out.still_running = task.state not in _ENDED
    # else: left as None. Falling back to the task's creation time would report
    # the hours it sat unstarted as time it spent working.

    blocks: List[Dict[str, Any]] = []
    read_any = False
    for record in records:
        try:
            blocks.extend((usage or usage_of)(record.get("cwd")))
            read_any = True
        except Exception:
            continue
    if not read_any or not blocks:
        out.unmeasured = 1
        return out

    out.input_tokens = sum(int(b.get("input_tokens") or 0) for b in blocks)
    out.output_tokens = sum(int(b.get("output_tokens") or 0) for b in blocks)
    out.cached_tokens = sum(int(b.get("cache_read_input_tokens") or 0)
                            for b in blocks)
    out.cache_write_tokens = sum(int(b.get("cache_creation_input_tokens") or 0)
                                 for b in blocks)
    return out


_ENDED = (tsk.VERIFIED, tsk.OFF, tsk.REFUSED, tsk.ARCHIVED)


def _ended_at(task: tsk.Task, now) -> float:
    """When it stopped. `updated_at` is the closest honest stamp — it is the
    moment the record last changed, which for an ended task is when it ended."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(task.updated_at).timestamp()
    except Exception:
        return now()


# ── totals ────────────────────────────────────────────────────────────

def for_agent(config: Config, agent: Agent, *,
              usage: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
              now=time.time) -> Spend:
    """Every task this worker holds, archived included.

    Archived tasks still count. They are finished, not undone — dropping them
    would make the total fall over time, which is the one thing a spend figure
    must never do.
    """
    total = Spend(agent_id=agent.id)
    rows = (tsk.all_of(config, agent) + tsk.all_of(config, agent, archived=True))
    for task in rows:
        one = for_task(config, agent, task, usage=usage, now=now)
        total.tasks += 1
        total.unmeasured += one.unmeasured
        if one.measured:
            total.input_tokens = (total.input_tokens or 0) + (one.input_tokens or 0)
            total.output_tokens = (total.output_tokens or 0) + (one.output_tokens or 0)
            total.cached_tokens = (total.cached_tokens or 0) + (one.cached_tokens or 0)
            total.cache_write_tokens = ((total.cache_write_tokens or 0)
                                        + (one.cache_write_tokens or 0))
        if one.wall_seconds is not None:
            total.wall_seconds = (total.wall_seconds or 0.0) + one.wall_seconds
        total.still_running = total.still_running or one.still_running
    return total


def across(config: Config, *,
           usage: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
           now=time.time) -> List[Spend]:
    """One row per worker that has held a task.

    A worker that has never run spent nothing, and six zero rows would bury the
    ones that did. The roster lives in `sarsi agents`; this answers "what did it
    cost", which is only a question about work that happened.
    """
    rows = [for_agent(config, agent, usage=usage, now=now)
            for agent in config.workers()]
    return [row for row in rows if row.tasks]
