"""`ai4science research …` — the CLI door onto the research-agent groups.

Thin, like `commands/sarsi.py`: every decision lives in
`harness.agents.research_agents`, and this surface only renders it. A research
agent is not one model — it is a **group** with reasoning, judging and embodied
members, and the one rule with teeth is that the group's ceiling is the lowest
of its members', not the agent's. This command makes both facts visible.

Agent-authored text (a charter's field, a member's refusal, a scope note) is
printed with `markup=False, highlight=False`, exactly as sarsi does: a refusal
is data, and `[twin]` is a name, not a style.
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ai4science.harness.agents.research_agents import registry as ra, group as g
# The everyday ceiling is what a research agent DECLARES before its group caps
# it. Read from the one place it is defined so a change there is felt here.
from ai4science.harness.agents.sarsi.registry import EVERYDAY_CEILING

app = typer.Typer(help="research-agent groups on this machine.", no_args_is_help=True)
console = Console()


@app.command("list", help="One row per research agent: field, members, group ceiling, benchmark.")
def list_cmd() -> None:
    """The seven at a glance. `ceiling` is the group's, `benchmark` is whether
    the agent has a runnable problem — both facts about the group, not the row."""
    agents = ra.build_all()
    table = Table(title="research agents", show_lines=False)
    table.add_column("Agent", style="cyan")
    table.add_column("Field")
    table.add_column("Members", justify="right")
    table.add_column("Ceiling")
    table.add_column("Benchmark")
    for name, agent in agents.items():
        # the field is agent-authored prose; render it, do not style it
        table.add_row(name, agent.charter.field, str(len(agent.group.members)),
                      agent.group.ceiling() or "—",
                      "yes" if agent.can_compute() else "no")
    console.print(table)


@app.command("show", help="One research agent in full: charter, the group ceiling stated as the rule, and its members.")
def show(name: str = typer.Argument(..., help="Research-agent name, e.g. imaging")) -> None:
    try:
        agent = ra.build(name)
    except KeyError:
        # Unknown: name the known ones and leave non-zero, so a shell `if` can
        # act on it without parsing text.
        console.print(f"[red]no research agent {name!r}[/red] — known: "
                      f"{', '.join(ra.NAMES)}")
        raise typer.Exit(code=2)

    ch = agent.charter
    group = agent.group

    console.print(f"{ch.name} — {ch.field}", style="cyan", markup=False,
                  highlight=False)
    console.print(f"subfields: {', '.join(ch.subfields)}", markup=False,
                  highlight=False)

    # The ceiling, stated as the rule: the agent's declared ceiling no longer
    # decides — the group's does, and it is the lowest any member's ACT needs.
    declared = EVERYDAY_CEILING
    grp = group.ceiling() or "—"
    effective = group.capped(declared)
    console.print(f"\nceiling: declared {declared} · group {grp} · "
                  f"effective {effective} — the lowest any member's act needs",
                  markup=False, highlight=False)

    # The members: what each acts on, its ceiling, and the one refusal that
    # defines it. A judging member shows `—` (it never acts, so it caps nothing).
    table = Table(title="members", show_lines=False)
    table.add_column("Member", style="cyan")
    table.add_column("Kind")
    table.add_column("Acts on")
    table.add_column("Ceiling")
    table.add_column("Its refusal")
    for m in group.members:
        table.add_row(m.name, m.kind.value, m.acts_on,
                      m.ceiling if m.ceiling is not None else "—", m.refusal)
    console.print(table)
    if any(m.kind is g.Kind.JUDGING for m in group.members):
        console.print("— a judging member never acts, so it does not cap the "
                      "group", style="dim", markup=False, highlight=False)

    # Refusals and scope, kept apart: a refusal travels to any agent in the
    # subfield; a scope note is about this agent's own role and does not.
    if ch.refusals:
        console.print("\nrefuses (these travel to any agent in the subfield):",
                      markup=False, highlight=False)
        for r in ch.refusals:
            console.print(f"  - {r}", markup=False, highlight=False)
    if ch.scope:
        console.print("\nnot its job (scope — does NOT travel):", markup=False,
                      highlight=False)
        for s in ch.scope:
            console.print(f"  - {s}", markup=False, highlight=False)
