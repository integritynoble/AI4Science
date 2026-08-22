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


# ── operation-specific readiness ─────────────────────────────────────────────
#
# "Am I ready?" is not a question with one answer. `readiness()` above asks it
# the way `assign` needs it asked, which is right for `assign` and wrong for
# everything else: archiving a task does not care whether an executor binary is
# on PATH, and writing a semantic memory does not care about either. A single
# global health check either blocks operations that had no need of the missing
# field, or passes operations that did.
#
# So the requirement is declared per operation, each field has ONE declared way
# to observe it, and the refresh is bounded. The rule that matters most is the
# last one: **retry exhaustion never becomes a guessed value.** A field that
# could not be measured stays `unmeasured`, and the operation is escalated or
# degraded — it is not run against a number nobody observed. [plan v3 §7.3]

#: operation -> the fields it actually requires.
REQUIRED_STATE: Dict[str, Tuple[str, ...]] = {
    "assign_executor": ("active_plan", "authority", "executor_reachable"),
    "archive_task": ("active_plan", "verification_state"),
    "guide_session": ("session_live",),
    "write_semantic_memory": ("provenance", "scope"),
}

#: Fields that may be permanently absent on some machines, and the operations
#: that stay legal without them. Declared, per §7.3, rather than discovered by
#: an operation failing in the field.
MAY_BE_ABSENT: Dict[str, Tuple[str, ...]] = {
    # No `claude`/`codex` binary on this host: the worker can still plan,
    # answer, archive and record — it cannot delegate.
    "executor_reachable": ("archive_task", "write_semantic_memory",
                           "guide_session"),
}

#: How many times a declared observation path is retried before the field is
#: left unmeasured. Bounded because an unreachable field must not loop forever.
DEFAULT_ATTEMPTS = 2


@dataclass(frozen=True)
class StateField:
    """One required field, and how it stands right now."""
    name: str
    validity: str            # fresh | stale | unmeasured | absent
    value: Any = None
    source: str = ""
    attempts: int = 0
    why: str = ""

    @property
    def ok(self) -> bool:
        return self.validity == "fresh"


@dataclass(frozen=True)
class Readiness:
    """The gate's answer for ONE operation."""
    operation: str
    ready: bool
    gaps: List[str] = field(default_factory=list)
    fields: List[StateField] = field(default_factory=list)
    exhausted: List[str] = field(default_factory=list)
    degraded_ok: bool = False   #: the only missing fields are declared-absent

    def as_record(self) -> Dict[str, Any]:
        return {"operation": self.operation, "ready": self.ready,
                "gaps": list(self.gaps), "exhausted": list(self.exhausted),
                "degraded_ok": self.degraded_ok,
                "fields": [{"name": f.name, "validity": f.validity,
                            "attempts": f.attempts, "source": f.source}
                           for f in self.fields]}


def _observe(config: Config, agent: Agent, name: str, *, task=None,
             context: Optional[Dict[str, Any]] = None,
             refreshed: Optional[Dict[str, bool]] = None) -> StateField:
    """The declared observation path for one field. One path per field, on
    purpose: two ways to learn the same thing is two things that can disagree."""
    ctx = context or {}
    if name == "authority":
        rows = {r["field"]: r for r in read_cached(agent.agent_dir)}
        rec = rows.get("authority")
        if rec is None:
            return StateField(name, "unmeasured", source="self_state.json",
                              why="authority has never been measured here")
        return StateField(name, rec.get("validity", "unmeasured"),
                          value=rec.get("value"), source="self_state.json",
                          why="" if rec.get("validity") == "fresh"
                              else "the ceiling may have changed since it was read")

    if name == "executor_reachable":
        found = {n: shutil.which(n) for n in ("claude", "codex")}
        live = [n for n, p in found.items() if p]
        if live:
            return StateField(name, "fresh", value=live, source="PATH")
        return StateField(name, "absent", value=[], source="PATH",
                          why="no `claude` or `codex` on PATH — there is "
                              "nothing here to delegate to")

    if name == "active_plan":
        if task is None:
            return StateField(name, "unmeasured", source="task store",
                              why="no task was named")
        try:
            plan = tsk.read_plan(config, agent, task)
        except Exception as e:
            return StateField(name, "unmeasured", source="task store",
                              why=f"plan could not be read: {e}")
        if plan is None:
            return StateField(name, "absent", source="task store",
                              why=f"task {task.id} has no plan — there is "
                                  f"nothing agreed to work from")
        if getattr(task, "awaiting", None):
            return StateField(name, "stale", value=task.plan_version,
                              source="task store",
                              why=f"task {task.id} is still awaiting grants: "
                                  + ", ".join(task.awaiting))
        return StateField(name, "fresh", value=task.plan_version,
                          source="task store")

    if name == "verification_state":
        if task is None:
            return StateField(name, "unmeasured", source="task store",
                              why="no task was named")
        if task.verdict:
            return StateField(name, "fresh", value=task.verdict.get("state"),
                              source="task verdict")
        if task.phase_verdicts:
            return StateField(name, "fresh",
                              value=f"{len(task.phase_verdicts)} phase verdicts",
                              source="task phase_verdicts")
        return StateField(name, "unmeasured", source="task store",
                          why=f"nothing has judged {task.id} — archiving it "
                              f"would file work no verifier ever saw")

    if name == "session_live":
        sess = (getattr(task, "session", None) or {}) if task is not None else {}
        nm = sess.get("name") or ""
        if nm:
            return StateField(name, "fresh", value=nm, source="task.session")
        return StateField(name, "absent", source="task.session",
                          why="no session on this task — there is nowhere to "
                              "deliver a steer")

    if name in ("provenance", "scope"):
        val = ctx.get(name)
        if val:
            return StateField(name, "fresh", value=val, source="caller")
        return StateField(name, "unmeasured", source="caller",
                          why=f"a semantic write with no {name} cannot be "
                              f"traced back or bounded")

    return StateField(name, "unmeasured", source="",
                      why=f"{name} has no declared observation path")


def _refresh(config: Config, agent: Agent, name: str) -> bool:
    """The declared way to make a field fresh again. False when there is none."""
    if name == "authority":
        try:
            sync(config, agent)
            return True
        except Exception:
            return False
    if name == "executor_reachable":
        return True          # re-probing PATH is the retry
    return False


def gate(config: Config, agent: Agent, operation: str, *, task=None,
         context: Optional[Dict[str, Any]] = None,
         attempts: int = DEFAULT_ATTEMPTS) -> Readiness:
    """Is the state this operation requires actually there? [§7.3]

    For each required field: fresh proceeds; stale or unmeasured gets the
    declared observation path up to `attempts` times; still unavailable leaves
    the field as it is and reports a gap. A field declared in `MAY_BE_ABSENT`
    for this operation does not block it — the operation was declared legal
    without it, in advance, rather than excused after the fact.
    """
    names = REQUIRED_STATE.get(operation)
    if names is None:
        return Readiness(operation=operation, ready=False,
                         gaps=[f"{operation!r} declares no required state — "
                               f"an operation the gate does not know is not "
                               f"one it can clear"])

    fields: List[StateField] = []
    gaps: List[str] = []
    exhausted: List[str] = []
    blocking_absent = False

    for name in names:
        tries = 0
        f = _observe(config, agent, name, task=task, context=context)
        while not f.ok and tries < attempts and f.validity != "absent":
            if not _refresh(config, agent, name):
                break
            tries += 1
            f = _observe(config, agent, name, task=task, context=context)
        f = StateField(f.name, f.validity, f.value, f.source, tries, f.why)
        fields.append(f)
        if f.ok:
            continue
        if tries >= attempts and attempts > 0:
            exhausted.append(name)
        if operation in MAY_BE_ABSENT.get(name, ()):
            # Declared legal without it. Reported anyway — a degraded run the
            # owner cannot see is indistinguishable from a normal one.
            gaps.append(f"{name} is {f.validity} ({f.why}) — {operation} is "
                        f"declared legal without it")
            continue
        blocking_absent = True
        gaps.append(f"{name} is {f.validity}"
                    + (f" — {f.why}" if f.why else "")
                    + (f" (observed {tries}x, still not available)" if tries else ""))

    ready = not blocking_absent
    return Readiness(operation=operation, ready=ready, gaps=gaps, fields=fields,
                     exhausted=exhausted,
                     degraded_ok=ready and bool(gaps))
