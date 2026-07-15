"""Manager console (A0 advisory): scope-route a demand, surface read-only
monitoring, and return an owner-gated proposal. Executes nothing — no open_run,
no sandbox, no set_criteria. The owner confirms a proposal before anything runs."""
from __future__ import annotations
import importlib
from typing import Optional
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.work.planner import DEFAULT_MODEL
from .scope import route
from .monitor import registry_view

_AGENT_SPEC_MODULES = ("work", "imaging", "research", "learning", "process_learning", "pocket", "machine")


def builtin_specs(plane: Optional[str] = None) -> list:
    """Collect the shipped routable AgentSpecs (skips any that fail to import). On the
    singularity product plane only matured agents are routable; on the ai4science
    platform (default) the whole fleet is. `plane` defaults to registry.current_plane()."""
    # imported lazily: registry.reload() imports the specs, which import this module —
    # a top-level import here would be circular.
    from ai4science.harness.agents.registry import current_plane
    plane = (plane or current_plane()).strip().lower()
    specs = []
    for mod in _AGENT_SPEC_MODULES:
        try:
            m = importlib.import_module(f"ai4science.harness.agents.specs.{mod}")
        except Exception:
            continue
        spec = m.AGENT
        if plane == "singularity" and not getattr(spec, "matured", False):
            continue
        specs.append(spec)
    return specs


def login_entry() -> AgentSpec:
    """The agent that greets the owner on login and routes their demand: the Manager.
    It is the single entry point in BOTH planes — the manager matures first, so it ships
    in the stable singularity product as well as the ai4science platform."""
    return importlib.import_module("ai4science.harness.agents.specs.manager").AGENT


def run_manager(*, demand: dict, client=None, specs=None, model: str = DEFAULT_MODEL,
                propose=None, plane: Optional[str] = None) -> dict:
    """demand = {"intent": str, "prefer"?: str}. Returns a PROPOSAL (no execution):
    the recommended accountable agent, the ranked candidates, a drafted demand
    skeleton, a rationale, and the read-only registry view. `specs` defaults to the
    agents exposed on the active plane (singularity = mature only, ai4science = all);
    injectable for tests. `propose` (optional) adds an LLM rationale."""
    intent = demand["intent"]
    prefer = demand.get("prefer")
    specs = specs if specs is not None else builtin_specs(plane)
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
