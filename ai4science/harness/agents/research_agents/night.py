"""One authorised night, driven from the outside.

This is the single call an owner's overnight schedule makes: "run *this* agent's
autonomous night." It is a thin, honest front for `autonomous_round`, and its
whole job is the two things a driver must not get wrong.

**It runs exactly one named agent, and only one that has something to run.** A
name it does not know is refused with the seven names it does know — read from
`registry.NAMES`, never hardcoded, so it cannot drift from the registry.
`imaging` is a name in that list but is the generalist and has no domain runner
(`benchmark_for('imaging')` raises), so a night for it has nothing to run and is
refused by name.

**It runs only on the owner's authorisation, and that authorisation is a
`Budget` supplied at the call site.** `build()` returns a fresh agent whose
switch is off, and the switch keeps its "on" state in memory only — there is no
persisted "on" to read back. So the owner's decision to let this night spend
cannot come from disk; it comes from the caller handing in a `Budget`, exactly
as a person would type `--budget UNITS` on the command line. With no budget the
driver refuses, and the refusal costs nothing: no client is constructed, no
workspace is made, `autonomous_round` is never reached. The only way the switch
goes on is `Switch.owner_turn_on(budget)` — the documented and only route. This
module never calls `agent_turn_on`, never touches a private field, never
bypasses `require_on`, and never invents a budget the caller did not give.

**The client is dependency-injected.** `client_factory` is a required keyword.
Nothing in here names a provider; the CLI wires a real one at the edge.

**Exactly one round.** `run_one_night` calls `autonomous_round`, not
`autonomous_loop`. A driver that looped would be deciding how many nights to run,
which is the owner's decision, expressed by scheduling this call.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from . import registry
from .budget import Budget
from .dual import Round, autonomous_round
from .runners import benchmark_for

#: The one label this driver signs the switch with, so an audit of who turned the
#: function on distinguishes a scheduled night from an interactive owner.
TURNED_ON_BY = "owner"


def _unknown_name_refusal(name: str) -> str:
    return ("no research agent %r — have: %s"
            % (name, ", ".join(registry.NAMES)))


def _imaging_refusal(name: str) -> str:
    return (
        "%s is the generalist and has no runnable benchmark of its own — "
        "benchmark_for(%r) has no domain runner, so an autonomous night has "
        "nothing to run. Its work is reached through its own AgentSpec, not "
        "this driver." % (name, name)
    )


def _no_budget_refusal(name: str) -> str:
    return (
        "%s: an autonomous night is refused without an owner-supplied budget. "
        "The switch is off on a fresh agent and keeps no persisted 'on' state, "
        "so the authorisation must come from the call site: construct a Budget "
        "and let the driver call Switch.owner_turn_on(budget) — on the command "
        "line, pass --budget UNITS. Nothing runs until it does." % name
    )


def run_one_night(name: str, *, client_factory: Callable[[int], Any],
                  workspace_root: Path, budget: Optional[Budget] = None,
                  agent: Optional["registry.ResearchAgent"] = None,
                  by: str = TURNED_ON_BY, **round_kwargs: Any) -> Round:
    """Run one agent's autonomous night, or refuse and spend nothing.

    `client_factory` and `workspace_root` are passed straight through to
    `autonomous_round`; `budget` is the owner's authorisation and `agent`, when
    given, lets a caller drive an already-built agent (the name still selects the
    benchmark and gates the refusals). Remaining keyword arguments — seeds,
    cost_per_seed, ledgers, and so on — reach `autonomous_round` unchanged.
    """
    # 1. A name we do not know. Refused with the seven we do, read from the
    #    registry so this list cannot fall out of step with it.
    if name not in registry.NAMES:
        raise KeyError(_unknown_name_refusal(name))

    # 2. A name we know that has no runnable benchmark. `imaging` is the
    #    generalist: it is in NAMES but `benchmark_for` has no domain runner for
    #    it, so the night has nothing to run. Refused by name, and BEFORE the
    #    switch — there is nothing to authorise.
    try:
        bench = benchmark_for(name)
    except KeyError:
        raise ValueError(_imaging_refusal(name)) from None

    # 3. No owner authorisation. Refuse before constructing any client, any
    #    workspace, or calling autonomous_round — nothing may run.
    if budget is None:
        raise PermissionError(_no_budget_refusal(name))

    # 4. Build the agent if the caller did not hand one in, and turn the switch
    #    on the one documented way. No private field, no agent_turn_on.
    if agent is None:
        agent = registry.build(name)
    agent.switch.owner_turn_on(budget, by=by)

    # 5. Exactly one round. Not a loop.
    return autonomous_round(agent, bench, client_factory=client_factory,
                            workspace_root=Path(workspace_root), **round_kwargs)


# ------------------------------------------------------------------------ CLI

def _control_plane_factory(socket_path: str) -> Callable[[int], Any]:
    """A real client factory for the command line, wired at the edge.

    The provider lives here, in the CLI, not in `run_one_night` — the driver
    itself takes whatever factory it is handed. Imported lazily so the module
    imports (and the no-budget refusal) never depend on the runtime being up."""
    from ai4science.harness.control_plane.client import ControlPlaneClient

    # Every seed opens its own run through the same governed client; the seed is
    # the benchmark's problem selector, not a reason for a second connection.
    def factory(_seed: int):
        return ControlPlaneClient(socket_path)

    return factory


def main(argv: Optional[list] = None) -> int:
    """`python -m ...night <agent> --budget N`. Never runs on import.

    With no `--budget` it prints the refusal and returns non-zero — it does not
    default a budget, because defaulting the owner's authorisation is the one
    thing this whole module exists to refuse."""
    parser = argparse.ArgumentParser(
        prog="python -m ai4science.harness.agents.research_agents.night",
        description="Run one research agent's autonomous night, once, with an "
                    "owner-supplied budget.")
    parser.add_argument("agent", help="the agent name (see registry.NAMES)")
    parser.add_argument("--budget", type=float, default=None,
                        help="owner authorisation, in the agent's units — the "
                             "switch stays off without it")
    parser.add_argument("--unit", default="gpu-hour",
                        help="unit the budget is denominated in")
    parser.add_argument("--socket", default=None,
                        help="path to the control-plane socket the run drives")
    parser.add_argument("--workspace-root", default="night-ws",
                        help="where the night's run workspaces are put")
    ns = parser.parse_args(argv)

    # Validate the name FIRST. Naming an agent runs nothing, so checking it
    # before --budget does not weaken the switch — it just means a typo hears
    # the name refusal (which lists the seven from registry.NAMES) instead of a
    # misleading missing-budget complaint. Order: unknown name -> imaging ->
    # budget -> socket.
    if ns.agent not in registry.NAMES:
        print(_unknown_name_refusal(ns.agent), file=sys.stderr)
        return 2

    try:
        benchmark_for(ns.agent)
    except KeyError:
        print(_imaging_refusal(ns.agent), file=sys.stderr)
        return 2

    if ns.budget is None:
        print(_no_budget_refusal(ns.agent), file=sys.stderr)
        return 2

    if ns.socket is None:
        print("%s: --socket is required to reach the control plane when a "
              "budget is given" % ns.agent, file=sys.stderr)
        return 2

    try:
        budget = Budget(ns.agent, units=ns.budget, unit=ns.unit)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        round_ = run_one_night(
            ns.agent, client_factory=_control_plane_factory(ns.socket),
            workspace_root=Path(ns.workspace_root), budget=budget)
    except (KeyError, ValueError, PermissionError) as e:
        print(str(e), file=sys.stderr)
        return 2

    print(round_.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
