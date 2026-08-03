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
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger, playbook as pb, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

LIMITS = ("competence beyond these measurements is unverified — nothing here "
          "is a claim about what I have not been measured doing")


@dataclass(frozen=True)
class Claim:
    field: str
    value: Any
    source: str          # required: where this was observed


def model(config: Config, agent: Agent, *,
          which: Callable[[str], Optional[str]] = shutil.which) -> List[Claim]:
    claims: List[Claim] = [
        Claim("agent", agent.id, "the registry"),
        Claim("role", agent.role, "the registry"),
        Claim("drives_sessions", agent.is_worker,
              "the registry — a manager has no path to ASG in code"),
        Claim("engines", _engines(which),
              "a real binary probe on this machine's PATH"),
    ]

    tasks = tsk.all_of(config, agent) if agent.is_worker else []
    claims.append(Claim("tasks_held", len(tasks), "this agent's task records"))
    claims.append(Claim("states", _states(tasks), "this agent's task records"))
    # s_C: written by the verifier, read here. What the agent claimed is absent.
    claims.append(Claim("verified",
                        sum(1 for t in tasks
                            if t.state == tsk.VERIFIED
                            and (t.verdict or {}).get("state") == "PASS"),
                        "verifier verdicts only"))

    claims.append(Claim("vault", _vault_counts(config, agent),
                        "the vault ledger — decisions, never secrets"))
    claims.append(Claim("outward", _outward_counts(config, agent),
                        "the outward ledger"))

    book = pb.read(config, agent)
    claims.append(Claim("playbook",
                        {"version": book.get("version"),
                         "params": book.get("params", {})},
                        "this agent's playbook on disk"))
    candidate = book.get("candidate")
    if candidate:
        claims.append(Claim("pending_candidate", candidate.get("rationale", ""),
                            "held, awaiting your signature"))
    claims.append(Claim("limits", LIMITS, "the honesty rule"))
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
        lines.append(f"  {claim.field}: {claim.value}   [{claim.source}]")
    if not agent.is_worker:
        # the invariant, reported as a fact about itself
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


# ── the probes ────────────────────────────────────────────────────────

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
