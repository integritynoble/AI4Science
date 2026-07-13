"""Appendix B sub-project 3b: turn an owner-minted, owner-activated foundry
record into a RUNNING domain agent. The record's signed manifest attests WHICH
domain the agent may run; this runner maps that domain to a registered domain
AgentSpec and runs it bound to the agent's identity + CP-derived ceiling. A
domain the record does not attest cannot be run here -- the harness never picks
the domain itself.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.agents.social.agent import run_social_task
from ai4science.harness.agents.work.agent import run_work_task
from ai4science.harness.agents.research.agent import run_research_task

_RANK = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}


def _profile_rank(profile: str) -> int:
    return _RANK.get(profile, -1)


@dataclass
class DomainEntry:
    min_profile: str
    run: Callable[..., dict]


def _run_imaging(*, client, store, agent_id, task_id, **kw) -> dict:
    return run_imaging_task(client=client, store=store, agent_id=agent_id, task_id=task_id, **kw)


def _run_social(*, client, store, agent_id, task_id, **kw) -> dict:
    return run_social_task(client=client, store=store, task_id=task_id, agent_id=agent_id, **kw)


def _run_work(*, client, store, agent_id, task_id, **kw) -> dict:
    return run_work_task(client=client, store=store, task_id=task_id, agent_id=agent_id, **kw)


def _run_research(*, client, store, agent_id, task_id, **kw) -> dict:
    return run_research_task(client=client, store=store, task_id=task_id, agent_id=agent_id, **kw)


# One real entry today; a second domain is just another key (the seam is generic).
DOMAIN_SPECS: dict[str, DomainEntry] = {
    "imaging": DomainEntry(min_profile="A1", run=_run_imaging),
    "social": DomainEntry(min_profile="A2", run=_run_social),
    "work": DomainEntry(min_profile="A1", run=_run_work),
    "research": DomainEntry(min_profile="A1", run=_run_research),
}


def run_foundry_agent(*, client, store, agent_id, task_id, **kw) -> dict:
    """Run the domain the foundry record attests, bound to the agent. Fail-closed:
    unknown/inactive agent, unattested/unknown domain, or a ceiling below the
    domain floor -> {"ok": False, ...} and NO run is opened."""
    rec = client.foundry_agent(agent_id)
    if not rec:
        return {"ok": False, "reason": "unknown foundry agent"}
    if rec.get("activation_state") != "active":
        return {"ok": False, "reason": "foundry agent is not active"}
    domain = rec.get("domain") or ""
    entry = DOMAIN_SPECS.get(domain)
    if entry is None:
        return {"ok": False, "reason": f"no runnable domain attested (domain={domain!r})"}
    ceiling = rec.get("ceiling", "")
    if _profile_rank(ceiling) < _profile_rank(entry.min_profile):
        return {"ok": False,
                "reason": f"ceiling {ceiling} below {domain} floor {entry.min_profile}"}
    result = entry.run(client=client, store=store, agent_id=agent_id, task_id=task_id, **kw)
    return {"ok": True, "agent_id": agent_id, "ceiling": ceiling, "result": result}
