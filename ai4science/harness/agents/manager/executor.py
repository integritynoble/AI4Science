"""Governed execution — turn an owner-approved routing into an actual agent run,
only through the control plane. Fail-closed, activated-agents-only, ceiling-bounded,
audited. This is NOT the Manager (A0, no authority); it is a separate executor the
owner explicitly wires in.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ai4science.harness.agents.foundry_runner import run_foundry_agent


def execute_demand(*, agent_id: str, demand, client, store=None,
                   task_id: Optional[str] = None, run_foundry=run_foundry_agent) -> Dict[str, Any]:
    """Fail-closed bridge to the governed foundry dispatch. No control-plane client
    ⇒ refuse and open no run. Otherwise delegate to run_foundry_agent, which
    enforces activation / attested domain / ceiling floor."""
    if client is None:
        return {"ok": False, "reason": "execution requires the governed control plane "
                                       "(start it: singularity up)"}
    demand_obj = {"intent": demand} if isinstance(demand, str) else demand
    return run_foundry(client=client, store=store, agent_id=agent_id,
                       task_id=task_id or f"console-{agent_id}", demand=demand_obj)


class GovernedExecutor:
    """Executes an owner-approved routing. `agent_ids` is the owner's explicit
    allowlist mapping agent NAME -> attested+activated foundry agent_id; only names
    in it can be executed from the console."""

    def __init__(self, *, client, store=None, agent_ids: Optional[Dict[str, str]] = None,
                 run_foundry=run_foundry_agent):
        self.client = client
        self.store = store
        self.agent_ids = dict(agent_ids or {})
        self.run_foundry = run_foundry

    def run(self, agent_name: str, demand) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "reason": "execution requires the governed control plane"}
        agent_id = self.agent_ids.get(agent_name)
        if not agent_id:
            return {"ok": False,
                    "reason": f"agent {agent_name!r} is not enabled for execution "
                              f"(owner must attest+activate it in the foundry and allowlist it)"}
        return execute_demand(agent_id=agent_id, demand=demand, client=self.client,
                              store=self.store, run_foundry=self.run_foundry)
