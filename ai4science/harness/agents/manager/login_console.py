"""The Manager on login — the ai4science console.

Realises the product directive "ai4science can first use the manager agent when
users login": on login the Manager greets the owner, shows the fleet it can route
to on the ACTIVE PLANE (ai4science = the whole factory; singularity = mature agents
only), and turns each demand into an owner-gated PROPOSAL. The Manager holds no
authority — `run_manager` proposes and executes nothing; the owner confirms a
proposal before any agent runs.

Deterministic: scope routing only, no LLM / network. Run the login demo with

    python3 -m ai4science.harness.agents.manager.login_console        # ai4science plane
    PWM_PLANE=singularity python3 -m ai4science.harness.agents.manager.login_console

This module is the reusable greeting the real `ai4science login` command can call
after authentication; the `main()` below is a self-contained demonstration of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ai4science.harness.agents import registry as _registry
from ai4science.harness.agents.manager.agent import builtin_specs, login_entry, run_manager
from ai4science.harness.agents.manager.monitor import registry_view


@dataclass(frozen=True)
class Greeting:
    """What the Manager presents the moment the owner logs in."""
    plane: str            # "ai4science" (factory) | "singularity" (product)
    manager: str          # the console agent's title
    profile: str          # its default interaction profile (I0 = propose-first)
    fleet: List[dict]     # read-only view of the agents it can route to on this plane
    approvals: tuple      # operations it must get owner approval for (never self-authorised)


def greet(*, plane: Optional[str] = None) -> Greeting:
    """Build the login greeting for `plane` (defaults to registry.current_plane()).

    The fleet is the Manager's routable set on that plane: on singularity only the
    matured agents are routable; on ai4science the whole platform is."""
    _registry.reload()
    plane = (plane or _registry.current_plane()).strip().lower()
    manager = login_entry()
    specs = builtin_specs(plane)
    return Greeting(
        plane=plane,
        manager=manager.title,
        profile=manager.default_profile,
        fleet=registry_view(specs),
        approvals=tuple(manager.approval_required_for),
    )


def handle_demand(intent: str, *, plane: Optional[str] = None,
                  prefer: Optional[str] = None) -> dict:
    """Route ONE login demand. Returns run_manager's proposal — the recommended
    accountable agent (or a documented capability gap), the ranked candidates, a
    drafted demand skeleton, and a rationale. Executes nothing."""
    demand = {"intent": intent}
    if prefer:
        demand["prefer"] = prefer
    return run_manager(demand=demand, plane=plane)


# --------------------------------------------------------------- plain-text rendering
# No `rich` dependency here so the greeting renders in any context (server logs,
# the demo, a plain pipe); the interactive CLI can re-render the same data with rich.

def render_greeting(g: Greeting) -> str:
    plane_note = ("the ai4science PLATFORM — the whole factory fleet"
                  if g.plane == "ai4science" else
                  "the singularity PRODUCT — matured agents only")
    lines = [
        f"  Welcome. I'm the {g.manager} — your console on {plane_note}.",
        f"  I propose and coordinate; I run nothing without your say-so "
        f"(approval required for: {', '.join(g.approvals)}).",
        f"  Tell me what you need and I'll route it to the accountable agent.",
        "",
        f"  Agents I can route to on this plane ({len(g.fleet)}):",
        f"    {'agent':<16}{'tier':<7}{'category':<10}what it's for",
    ]
    for a in sorted(g.fleet, key=lambda r: r["name"]):
        kw = ", ".join(a["keywords"][:4]) if a["keywords"] else a["title"]
        lines.append(f"    {a['name']:<16}{a['tier']:<7}{a['category']:<10}{kw}")
    return "\n".join(lines)


def render_proposal(intent: str, proposal: dict) -> str:
    rec = proposal.get("recommended_agent")
    if rec:
        ranked = ", ".join(f"{n}({s:.2f})" for n, s in proposal.get("ranked", [])) or "—"
        return (f'  you: "{intent}"\n'
                f"  Manager -> PROPOSAL: route to '{rec}'  (owner confirmation required to run)\n"
                f"            draft demand : {proposal.get('draft_demand')}\n"
                f"            candidates   : {ranked}\n"
                f"            rationale    : {proposal.get('rationale')}")
    return (f'  you: "{intent}"\n'
            f"  Manager -> CAPABILITY GAP on this plane: {proposal.get('gap')}\n"
            f"            (nothing is attempted out of scope — the demand is held for you)")


# ----------------------------------------------------------------------------- demo
def _demo() -> None:
    def hr(t): print("\n" + "=" * 74 + f"\n{t}\n" + "=" * 74)

    hr("ai4science LOGIN — the Manager greets you (platform plane, the whole fleet)")
    g = greet(plane="ai4science")
    print(render_greeting(g))

    hr("YOU HAND THE MANAGER DEMANDS — it routes each to an owner-gated proposal")
    demands = [
        "help me with some coding work on my data files",
        "reconstruct my CASSI computational imaging scene",
        "tutor and quiz me to study for my exam",
        "install Claude and grant permission during setup",
    ]
    for intent in demands:
        print(render_proposal(intent, handle_demand(intent, plane="ai4science")))
        print()

    hr("SAME DEMAND, PRODUCT PLANE — singularity exposes matured agents only")
    print("  singularity ships mature agents only (manager + machine today); the")
    print("  sandboxed specialists keep improving in ai4science until they're promoted.\n")
    g2 = greet(plane="singularity")
    print(render_greeting(g2))
    print()
    imaging_demand = "reconstruct my CASSI computational imaging scene"
    print(render_proposal(imaging_demand, handle_demand(imaging_demand, plane="singularity")))
    print()
    machine_demand = "install Claude and grant permission during setup"
    print(render_proposal(machine_demand, handle_demand(machine_demand, plane="singularity")))

    print("\n" + "-" * 74)
    print("  The Manager proposed everything and executed nothing — the owner confirms")
    print("  a proposal before any agent runs. That is the ai4science login experience.")


def main() -> None:  # entry point for `python3 -m ...`
    _demo()


if __name__ == "__main__":
    main()
