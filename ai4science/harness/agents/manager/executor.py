"""Governed execution — turn an owner-approved routing into an actual agent run,
only through the control plane. Fail-closed, activated-agents-only, ceiling-bounded,
audited. This is NOT the Manager (A0, no authority); it is a separate executor the
owner explicitly wires in.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ai4science.harness.agents.foundry_runner import run_foundry_agent
from ai4science.harness.agents.manager.input_staging import prepare_run_kwargs


def execute_demand(*, agent_id: str, client, store=None, task_id: Optional[str] = None,
                   run_kwargs: Optional[Dict[str, Any]] = None,
                   run_foundry=run_foundry_agent) -> Dict[str, Any]:
    """Fail-closed bridge to the governed foundry dispatch. No control-plane client
    ⇒ refuse and open no run. Otherwise delegate to run_foundry_agent (which
    enforces activation / attested domain / ceiling floor), passing the
    agent-appropriate `run_kwargs` through to its runner."""
    if client is None:
        return {"ok": False, "reason": "execution requires the governed control plane "
                                       "(start it: singularity up)"}
    return run_foundry(client=client, store=store, agent_id=agent_id,
                       task_id=task_id or f"console-{agent_id}", **(run_kwargs or {}))


class GovernedExecutor:
    """Executes an owner-approved routing. `agent_ids` is the owner's explicit
    allowlist mapping agent NAME -> attested+activated foundry agent_id; only names
    in it can be executed from the console."""

    def __init__(self, *, client, store=None, agent_ids: Optional[Dict[str, str]] = None,
                 default_sources: Optional[Dict[str, dict]] = None, run_foundry=run_foundry_agent):
        self.client = client
        self.store = store
        self.agent_ids = dict(agent_ids or {})
        # owner-configured default inputs per agent (e.g. imaging -> the current
        # scene) so an input agent can run from a chat demand that carries no files;
        # explicit sources override these.
        self.default_sources = dict(default_sources or {})
        self.run_foundry = run_foundry

    def run(self, agent_name: str, demand, sources: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.client is None:
            return {"ok": False, "reason": "execution requires the governed control plane"}
        agent_id = self.agent_ids.get(agent_name)
        if not agent_id:
            return {"ok": False,
                    "reason": f"agent {agent_name!r} is not enabled for execution "
                              f"(owner must attest+activate it in the foundry and allowlist it)"}
        merged = {**self.default_sources.get(agent_name, {}), **(sources or {})}
        prep = prepare_run_kwargs(agent_name, demand, merged)
        if not prep["ok"]:                      # required input missing -> no run
            return {"ok": False, "reason": prep["reason"], "missing": prep.get("missing", [])}
        return execute_demand(agent_id=agent_id, client=self.client, store=self.store,
                              run_kwargs=prep["kwargs"], run_foundry=self.run_foundry)
