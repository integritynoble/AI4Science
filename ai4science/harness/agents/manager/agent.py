"""Manager console (A0 advisory): scope-route a demand, surface read-only
monitoring, and return an owner-gated proposal. Executes nothing — no open_run,
no sandbox, no set_criteria. The owner confirms a proposal before anything runs."""
from __future__ import annotations
import importlib
from ai4science.harness.agents.work.planner import DEFAULT_MODEL
from .scope import route
from .monitor import registry_view

_AGENT_SPEC_MODULES = ("work", "imaging", "research", "learning", "process_learning", "pocket")


def builtin_specs() -> list:
    """Collect the shipped routable AgentSpecs (skips any that fail to import)."""
    specs = []
    for mod in _AGENT_SPEC_MODULES:
        try:
            m = importlib.import_module(f"ai4science.harness.agents.specs.{mod}")
            specs.append(m.AGENT)
        except Exception:
            continue
    return specs


def run_manager(*, demand: dict, client=None, specs=None, model: str = DEFAULT_MODEL,
                propose=None) -> dict:
    """demand = {"intent": str, "prefer"?: str}. Returns a PROPOSAL (no execution):
    the recommended accountable agent, the ranked candidates, a drafted demand
    skeleton, a rationale, and the read-only registry view. `specs` defaults to the
    shipped agents; injectable for tests. `propose` (optional) adds an LLM rationale."""
    intent = demand["intent"]
    prefer = demand.get("prefer")
    specs = specs if specs is not None else builtin_specs()
    routing = route(intent, specs, prefer=prefer)
    recommended = routing["primary"]
    draft = {"agent": recommended, "objective": intent} if recommended else None
    if recommended:
        rationale = f"routed to {recommended!r} by scope match (owner confirmation required to run)"
    else:
        rationale = routing["gap"]
    if propose is not None and recommended:
        try:
            extra = propose(client, intent, recommended)
            if extra:
                rationale = extra
        except Exception:
            pass
    return {"recommended_agent": recommended, "ranked": routing["ranked"],
            "gap": routing["gap"], "draft_demand": draft, "rationale": rationale,
            "registry": registry_view(specs)}
