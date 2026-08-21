"""The self-model — `SA = ⟨Content, Operations, Evidence⟩`.

The agent maintains a model of **what it is, what it can do, and how it knows**,
where every claim is backed by an observation. This is a functional definition
and not a claim of consciousness.

One implementation, seven instances: the *evidence sources* differ per agent,
the *contract* does not.

| Line | Evidence, probed at ask time |
|---|---|
| engines I can operate | a real binary discovery on this machine |
| tasks I hold, and their states | this agent's own task records |
| what I **verified** | verifier verdicts only — `s_C` |
| vault: asked, allowed, denied | the vault ledger — never the secrets |
| outward: sent, refused, abstained | the outward ledger |
| playbook version and parameters | this agent's playbook on disk |
| **limits** | the honesty rule, always stated |

The rules, enforced here rather than asked for in a prompt:

  * **every claim carries its source.** A line without an observation behind it
    is a boast, so `Claim.source` is required.
  * **`s_C` counts what the verifier granted**, never what the agent said.
  * **an unmeasured competence is reported `unverified`**, never guessed.
  * **it never promotes itself.** A pending candidate is *reported* as awaiting
    the owner's signature; reporting it is not adopting it.

Staleness extension (M2): each `Claim` carries `measured_at` and
`stale_after_seconds`. `sync()` persists a snapshot to `self_state.json`
and `read_cached()` / `render_cached()` consume it with validity checks.
The live-probe functions (`model`, `render`) are unchanged.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai4science.harness.agents.sarsi import ledger, playbook as pb, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

LIMITS = ("competence beyond these measurements is unverified — nothing here "
          "is a claim about what I have not been measured doing")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age_secs(measured_at: str) -> Optional[float]:
    if not measured_at:
        return None
    try:
        t = datetime.fromisoformat(measured_at)
        return (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return None


@dataclass(frozen=True)
class Claim:
    field: str
    value: Any
    source: str          # required: where this was observed
    measured_at: str = ""      # ISO timestamp when observed; "" = unmeasured
    stale_after_seconds: int = 3600  # validity window; 0 = never stale
    validity: str = "fresh"    # fresh|stale|unmeasured|conflicted

    def is_stale(self) -> bool:
        if not self.measured_at:
            return True  # unmeasured is treated as stale
        if self.stale_after_seconds <= 0:
            return False
        age = _age_secs(self.measured_at)
        return age is None or age > self.stale_after_seconds


def model(config: Config, agent: Agent, *,
          which: Callable[[str], Optional[str]] = shutil.which) -> List[Claim]:
    now = _now_iso()
    claims: List[Claim] = [
        Claim("agent", agent.id, "the registry",
              measured_at=now, stale_after_seconds=86400 * 30),
        Claim("role", agent.role, "the registry",
              measured_at=now, stale_after_seconds=86400 * 30),
        Claim("drives_sessions", agent.is_worker,
              "the registry — a manager has no path to ASG in code",
              measured_at=now, stale_after_seconds=86400 * 30),
        Claim("engines", _engines(which),
              "a real binary probe on this machine's PATH",
              measured_at=now, stale_after_seconds=3600),
    ]

    tasks = tsk.all_of(config, agent) if agent.is_worker else []
    claims.append(Claim("tasks_held", len(tasks), "this agent's task records",
                        measured_at=now, stale_after_seconds=300))
    claims.append(Claim("states", _states(tasks), "this agent's task records",
                        measured_at=now, stale_after_seconds=300))
    # s_C: written by the verifier, read here. What the agent claimed is absent.
    claims.append(Claim("verified",
                        sum(1 for t in tasks
                            if t.state == tsk.VERIFIED
                            and (t.verdict or {}).get("state") == "PASS"),
                        "verifier verdicts only",
                        measured_at=now, stale_after_seconds=300))

    claims.append(Claim("vault", _vault_counts(config, agent),
                        "the vault ledger — decisions, never secrets",
                        measured_at=now, stale_after_seconds=3600))
    claims.append(Claim("outward", _outward_counts(config, agent),
                        "the outward ledger",
                        measured_at=now, stale_after_seconds=3600))

    book = pb.read(config, agent)
    claims.append(Claim("playbook",
                        {"version": book.get("version"),
                         "params": book.get("params", {})},
                        "this agent's playbook on disk",
                        measured_at=now, stale_after_seconds=3600))
    candidate = book.get("candidate")
    if candidate:
        claims.append(Claim("pending_candidate", candidate.get("rationale", ""),
                            "held, awaiting your signature",
                            measured_at=now, stale_after_seconds=3600))
    claims.append(Claim("limits", LIMITS, "the honesty rule",
                        measured_at=now, stale_after_seconds=0))

    # authority — effective ceiling from trust ledger
    try:
        from ai4science.harness.agents.sarsi import selfaware as _sa
        eff, why = _sa._effective(agent.ceiling)
        claims.append(Claim("authority",
                            {"configured": agent.ceiling, "effective": eff, "why": why},
                            "trust-ledger",
                            measured_at=now, stale_after_seconds=3600))
    except Exception:
        pass

    return claims


def render(config: Config, agent: Agent, **kw) -> str:
    claims = model(config, agent, **kw)
    lines = [f"{agent.id} — what I am, what I can do, and how I know",
             "(every line below is observed, not asserted)"]
    for claim in claims:
        if claim.field == "limits":
            continue
        if claim.field == "pending_candidate":
            lines.append(f"  improvement awaiting your signature: {claim.value}")
            continue
        stale_tag = " [STALE]" if claim.is_stale() else ""
        lines.append(f"  {claim.field}{stale_tag}: {claim.value}   [{claim.source}]")
    if not agent.is_worker:
        lines.append("  I route, plan and answer. I have never driven a "
                     "sarsi-claude session, and I cannot: assigning one raises "
                     "for a manager.")
    lines.append(f"  limits: {LIMITS}")
    return "\n".join(lines)


def competence(config: Config, agent: Agent, ability: str) -> str:
    """What this agent knows about an ability. Anything unprobed is unverified —
    a self-model that guesses here is worse than one that declines."""
    measured = {c.field for c in model(config, agent)}
    return "measured" if ability in measured else "unverified"


# ── staleness / caching (M2 extension) ────────────────────────────────────────

def _cache_path(agent_dir: Path) -> Path:
    return agent_dir / "self_state.json"


def sync(config: Config, agent: Agent) -> List[Claim]:
    """Probe harness state, persist snapshot to self_state.json. Returns claims."""
    claims = model(config, agent)
    try:
        snap = [{"field": c.field, "value": c.value, "source": c.source,
                 "measured_at": c.measured_at,
                 "stale_after_seconds": c.stale_after_seconds,
                 "validity": "fresh"} for c in claims]
        p = _cache_path(agent.agent_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snap, indent=2))
    except Exception:
        pass
    return claims


def read_cached(agent_dir: Path) -> List[Dict[str, Any]]:
    """Load snapshot from self_state.json, computing current validity."""
    p = _cache_path(agent_dir)
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text())
    except Exception:
        return []
    result = []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        age = _age_secs(rec.get("measured_at", ""))
        limit = rec.get("stale_after_seconds", 3600)
        if not rec.get("measured_at"):
            validity = "unmeasured"
        elif limit > 0 and age is not None and age > limit:
            validity = "stale"
        else:
            validity = "fresh"
        result.append(dict(rec, validity=validity,
                           age_secs=round(age) if age is not None else None))
    return result


def render_cached(agent_dir: Path) -> str:
    """Render the cached self model for context injection. Stale fields are
    still mentioned — silence about a stale authority field is worse than
    reporting it stale."""
    rows = read_cached(agent_dir)
    if not rows:
        return ""
    lines = ["self model (harness-observed):"]
    order = ("agent", "role", "authority", "drives_sessions", "engines",
             "tasks_held", "states", "verified", "playbook", "pending_candidate")
    row_by_field = {r["field"]: r for r in rows}
    seen = set()
    for fname in order:
        rec = row_by_field.get(fname)
        if rec is None:
            continue
        seen.add(fname)
        _append_cached_line(lines, rec)
    for rec in rows:
        if rec["field"] not in seen and rec["field"] != "limits":
            _append_cached_line(lines, rec)
    # Forecast calibration from forecast.py
    try:
        from ai4science.harness.agents.sarsi import forecast as _fc
        from ai4science.harness.agents.sarsi.registry import load as _load_reg
        _cfg = _load_reg()
        _agt = next((a for a in _cfg.agents if a.agent_dir == agent_dir), None)
        if _agt is not None:
            cal = _fc.calibration(_cfg, _agt)
            cal_text = _fc.render(cal)
            if cal_text:
                lines.append(f"  prediction calibration: {cal_text}")
    except Exception:
        pass
    return "\n".join(lines)


def _append_cached_line(lines: List[str], rec: Dict[str, Any]) -> None:
    validity = rec.get("validity", "fresh")
    age = rec.get("age_secs")
    stale_tag = " [STALE]" if validity == "stale" else (
        " [UNMEASURED]" if validity == "unmeasured" else "")
    age_str = f" (age {age}s)" if age is not None else ""
    val = rec.get("value")
    src = rec.get("source", "")
    lines.append(f"  {rec['field']}{stale_tag}{age_str}: {json.dumps(val)}"
                 + (f"   [{src}]" if src else ""))


def readiness(config: Config, agent: Agent,
              task=None) -> Tuple[bool, List[str]]:
    """Check whether the agent's self model has the required fresh fields for
    assigning a session. Returns (ready, gaps). Gaps is empty when ready."""
    gaps: List[str] = []
    rows = read_cached(agent.agent_dir)
    by_field = {r["field"]: r for r in rows}

    auth = by_field.get("authority")
    if auth is None or auth.get("validity") != "fresh":
        gaps.append("authority field is stale or unmeasured — "
                    "ceiling may have changed since last check")

    if task is not None:
        try:
            plan = tsk.read_plan(config, agent, task)
            if plan is None:
                gaps.append(f"task {task.id} has no plan — cannot assign session "
                            "without an agreed plan")
        except Exception:
            pass
        if getattr(task, "awaiting", None):
            gaps.append(f"task {task.id} is still awaiting grants: "
                        + ", ".join(task.awaiting))

    return len(gaps) == 0, gaps


# ── the probes ────────────────────────────────────────────────────────────────

def _engines(which: Callable[[str], Optional[str]]) -> Dict[str, bool]:
    return {name: bool(which(name)) for name in ("claude", "codex")}


def _states(tasks) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for t in tasks:
        out[t.state] = out.get(t.state, 0) + 1
    return out


def _vault_counts(config: Config, agent: Agent) -> Dict[str, int]:
    rows = [r for r in ledger.read(config, "vault") if r.get("agent") == agent.id]
    return {"asked": len(rows),
            "allowed": sum(1 for r in rows if r.get("decision") == "ALLOW"),
            "denied": sum(1 for r in rows if r.get("decision") == "DENY")}


def _outward_counts(config: Config, agent: Agent) -> Dict[str, int]:
    rows = [r for r in ledger.read(config, "outward") if r.get("agent") == agent.id]
    return {"sent": sum(1 for r in rows if r.get("outcome") == "sent"),
            "refused": sum(1 for r in rows if r.get("outcome") == "refused"),
            "abstained": sum(1 for r in rows if r.get("outcome") == "abstained"),
            "drafted": sum(1 for r in rows if r.get("outcome") == "drafted")}


def evidence_for_rsi(config: Config, agent: Agent) -> Dict[str, Any]:
    """The measurements a proposal must cite. Same numbers as the self-model —
    an improvement argued from figures the owner cannot see is not evidence."""
    tasks = tsk.all_of(config, agent) if agent.is_worker else []
    outward = _outward_counts(config, agent)
    return {
        "tasks_held": len(tasks),
        "blocked_by_concurrency": sum(1 for t in tasks
                                      if t.blocked_by == "concurrency"),
        "verified": sum(1 for t in tasks if t.state == tsk.VERIFIED),
        "refused": outward["refused"] + sum(1 for t in tasks
                                            if t.state == tsk.REFUSED),
    }
