"""`ai4science sarsi …` — the CLI door onto the sarsi agents.

Thin by design: every decision lives in `harness.agents.sarsi`, so the CLI and
the Telegram surface reach the same agent through the same code. A surface is a
door, not a scope.
"""
from __future__ import annotations

from typing import List, Optional

import json
import pathlib
import typer
from rich.console import Console
from rich.table import Table

from ai4science.harness.agents.sarsi import admin, registry as reg
from ai4science.harness.agents.sarsi import backends as backends_mod

app = typer.Typer(help="sarsi worker agents on this machine.", no_args_is_help=True)
console = Console()


def _load() -> reg.Config:
    try:
        return reg.load()
    except reg.ConfigError as e:
        console.print(f"[red]registry error:[/red] {e}")
        raise typer.Exit(code=2)


@app.command("init", help="Write the registry and create each agent's directories.")
def init(owner_id: str = typer.Option("", "--owner-id",
                                      help="Your Telegram user id — the only id whose messages are honored."),
         reconcile: bool = typer.Option(False, "--reconcile",
                                        help="Add roster agents a later release shipped, leaving everything else alone.")) -> None:
    if reconcile:
        # The other half of init's refusal. It never rewrites what is there —
        # an agent the owner retired or re-ceilinged is theirs — so this is
        # safe to run after any upgrade.
        try:
            added = admin.reconcile()
        except Exception as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2)
        if not added:
            console.print("nothing to add — every roster agent is already here")
            return
        for agent_id in added:
            console.print(f"added [cyan]{agent_id}[/cyan]")
        console.print("their directories and bindings are in place; "
                      "[cyan]ai4science sarsi agents[/cyan] shows them")
        return
    if not owner_id.strip():
        console.print("[red]--owner-id is required to write a new registry "
                      "(or pass --reconcile to top up an existing one)[/red]")
        raise typer.Exit(code=2)
    try:
        config = admin.init(owner_id=owner_id)
    except admin.AlreadyInitialised as e:
        console.print(f"[yellow]{e}[/yellow]")
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    console.print(f"wrote [cyan]{config.path}[/cyan] — {len(config.agents)} agents")
    console.print("add a bot token per agent, then: [cyan]ai4science sarsi agents --bindings[/cyan]")


@app.command("agents", help="List the agents, their ceilings, and (with --bindings) how each is reached.")
def agents(bindings: bool = typer.Option(False, "--bindings",
                                         help="Show each agent's channel bindings.")) -> None:
    from ai4science.harness.agents.sarsi.registry import EVERYDAY_CEILING
    config = _load()
    table = Table(title="sarsi agents", show_lines=False)
    table.add_column("Agent", style="cyan")
    table.add_column("Role")
    table.add_column("Drives sessions")
    # which ai4science agent spec its sessions run — the seven are a layer over
    # the specs the registry already ships, not a second stack beside them
    table.add_column("Built on")
    table.add_column("Ceiling")
    table.add_column("Telegram")
    rows = admin.agent_rows(config)
    for row in rows:
        # the invariant, shown rather than assumed: the manager may not execute
        drives = "[green]yes[/green]" if row["drives_sessions"] else "[yellow]no[/yellow]"
        # Retired is shown here rather than dropped from the list: an agent that
        # vanished would read as a machine that lost one. It also stops claiming
        # it drives sessions — nothing can be given to it to drive one with.
        if row.get("retired"):
            # In this column rather than appended to the role: `worker
            # (retired)` wraps to a second line in a narrow terminal, and a
            # marker that only shows on a wide console is not a marker. The
            # column asks what it does, and this answers it.
            drives = "[yellow]retired[/yellow]"
        # the supervision loop reads Claude Code's TUI; on another interface it
        # can start the session but must not claim it can drive it
        built_on = row["spec"]
        if not row.get("unattended", True):
            built_on = f"{built_on} [yellow](attended)[/yellow]"
        # what it would actually run at, not what the file asks for
        ceiling = row["ceiling"]
        if row.get("ceiling_effective") != ceiling:
            ceiling = f"{row['ceiling_effective']} (asked {ceiling})"
        # Above what the seven run at. An existing registry keeps its stored
        # ceiling — silently lowering a recorded permission is the same class
        # of move as silently raising one — so the owner is TOLD, here, in the
        # listing they already read, rather than finding out from a gate that
        # never fired. Marked in the cell so a narrow terminal cannot wrap the
        # warning off the row it belongs to.
        if row.get("elevated"):
            ceiling = f"{ceiling} [yellow]![/yellow]"
        table.add_row(row["id"], row["role"], drives, built_on, ceiling,
                      row["telegram"])
    console.print(table)
    if any(r.get("elevated") for r in rows):
        raised = ", ".join(r["id"] for r in rows if r.get("elevated"))
        console.print(f"\n[yellow]![/yellow] above the everyday ceiling "
                      f"({EVERYDAY_CEILING}): {raised}", markup=True)
        console.print(f"[dim]  an elevated agent may run consequential "
                      f"commands — git push, installs, sudo — without asking\n"
                      f"  bring one down with: ai4science sarsi ceiling <agent> "
                      f"{EVERYDAY_CEILING}[/dim]")
    if bindings:
        # printed as lines rather than a table column: a wrapped cell can split
        # `telegram:work` across two rows, and a binding you cannot read is a
        # binding you cannot check.
        console.print("\nbindings — how each agent is reached:")
        width = max(len(r["id"]) for r in rows)
        for row in rows:
            reached = " ".join(row["bindings"]) or "[yellow]unreachable[/yellow]"
            console.print(f"  {row['id']:<{width}}  {reached}", highlight=False)


@app.command("ask", help="Say something to one agent from the CLI — the same door as its bot.")
def ask(agent_id: str = typer.Argument(..., help="Agent id, e.g. sarsi-worker"),
        text: str = typer.Argument(..., help="What to say")) -> None:
    from ai4science.harness.agents.sarsi import gateway, ownerlog, router

    config = _load()
    decision = router.decide(config, channel=router.CLI_CHANNEL, account_id=agent_id)
    if decision.dropped:
        console.print(f"[red]no agent {agent_id!r}[/red] — known: "
                      f"{', '.join(sorted(config.agents))}")
        raise typer.Exit(code=2)
    agent = decision.agent
    ownerlog.append(config, agent, text, surface=router.CLI_CHANNEL)
    reply = gateway.handle(config, agent=agent, text=text,
                           surface=router.CLI_CHANNEL)
    if reply:
        # Both doors record both roles, or the transcript depends on which door
        # the owner happened to use.
        ownerlog.reply(config, agent, reply, surface=router.CLI_CHANNEL)
    # markup off: an agent's reply is data. `[abraham]` is a name, not a style.
    console.print(reply or "(no reply)", markup=False, highlight=False)


@app.command("do", help="Hand one worker a directive: a goal, and what it will need.")
def do(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
       goal: str = typer.Argument(..., help="The goal — one sentence, not the conversation"),
       tool: List[str] = typer.Option(None, "--tool",
                                      help="A tool the work needs (repeatable)."),
       secret: List[str] = typer.Option(None, "--secret",
                                        help="A secret the work will need (repeatable)."),
       workdir: str = typer.Option("", "--workdir",
                                   help="Where the work happens — evidence is gathered from here."),
       plan_steps: Optional[int] = typer.Option(None, "--plan-steps",
                                    help="Stop PLANNING after this many steps "
                                         "(no default). Counted apart from "
                                         "--steps, which is the work."),
       plan_minutes: Optional[int] = typer.Option(None, "--plan-minutes",
                                    help="Stop planning after this many minutes "
                                         "(no default)."),
       steps: Optional[int] = typer.Option(None, "--steps",
                                           help="Stop after this many steps (no default)."),
       minutes: Optional[int] = typer.Option(None, "--minutes",
                                             help="Stop after this many minutes (no default)."),
       after: List[str] = typer.Option(None, "--after",
                                       help="Wait until <agent>/<task> is VERIFIED (repeatable)."),
       backend: str = typer.Option("", "--backend",
                                   help="Which engine runs the session: "
                                        "sarsi-pwm (ai4science, the default) or "
                                        "sarsi-claude (Anthropic's claude binary).")) -> None:
    from pathlib import Path

    from ai4science.harness.agents.sarsi import worker

    root = None
    if workdir.strip():
        root = Path(workdir).expanduser()
        if not root.is_dir():
            # Refused here rather than at verification time: a folder that is
            # not there makes every later verdict UNVERIFIED, for a reason
            # stated nowhere near the mistake that caused it.
            console.print(f"[red]no such directory: {workdir}[/red]")
            raise typer.Exit(code=2)
        root = str(root.resolve())

    for name, value in (("--steps", steps), ("--minutes", minutes),
                        ("--plan-steps", plan_steps),
                        ("--plan-minutes", plan_minutes)):
        if value is not None and value < 1:
            # A budget of zero stops the task before it starts. That is not a
            # budget; it is a way to file work that can never run.
            console.print(f"[red]{name} must be at least 1[/red]")
            raise typer.Exit(code=2)

    config = _load()
    agent = config.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]no agent {agent_id!r}[/red] — known: "
                      f"{', '.join(sorted(config.agents))}")
        raise typer.Exit(code=2)
    try:
        directive = worker.Directive(agent_id=agent_id, goal=goal,
                                     requires_tools=list(tool or []),
                                     requires_secrets=list(secret or []))
    except worker.BadDirective as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    try:
        out = worker.admit(config, agent, directive)
    except worker.NotAWorker as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    if not out.admitted:
        # NOM: say what is missing, by name, and do not queue it.
        console.print(out.message, style="yellow", markup=False, highlight=False)
        console.print("not queued — nothing is waiting on this", style="dim")
        raise typer.Exit(code=1)

    from ai4science.harness.agents.sarsi import plan as pl, task as tsk

    waits = []
    if after:
        from ai4science.harness.agents.sarsi import depends as _dep
        try:
            waits = _dep.check(config, agent, list(after))
        except (_dep.Unknown, _dep.Cycle) as e:
            # Refused HERE, not at start: a task that can never run must say so
            # while somebody is still looking at it.
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2)

    draft = pl.draft(directive)
    if waits:
        from dataclasses import replace as _replace2
        draft = _replace2(draft, depends_on=waits)
    if root or steps or minutes or plan_steps or plan_minutes:
        from dataclasses import replace as _replace
        draft = _replace(draft, work_root=root or draft.work_root,
                         max_steps=steps, max_minutes=minutes,
                         max_plan_steps=plan_steps,
                         max_plan_minutes=plan_minutes,
                         depends_on=draft.depends_on)
    # The backend belongs to the TASK: one worker runs many, and which engine
    # ran a given one is a fact about that one. Refused here rather than at run
    # time, when the owner has confirmed and walked away.
    try:
        made = tsk.create(config, agent, directive, backend=backend)
    except backends_mod.NoSuchBackend as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=1)
    t = tsk.attach_plan(config, agent, made, draft)
    t = tsk.start(config, agent, t)
    console.print(f"{agent_id} holds {t.id} — {t.state}", markup=False, highlight=False)
    if root:
        console.print(f"evidence will be gathered from {root}", style="dim",
                      markup=False, highlight=False)
    if steps or minutes:
        limits = ([f"{steps} steps"] if steps else []) + \
                 ([f"{minutes} minutes"] if minutes else [])
        console.print(f"budget: {', '.join(limits)} for the WORK, counted from "
                      f"when planning ends — it stops and keeps its "
                      f"plan, it does not fail", style="dim", markup=False,
                      highlight=False)
    if plan_steps or plan_minutes:
        limits = ([f"{plan_steps} steps"] if plan_steps else []) + \
                 ([f"{plan_minutes} minutes"] if plan_minutes else [])
        console.print(f"planning budget: {', '.join(limits)} — spent apart "
                      f"from the work's", style="dim", markup=False,
                      highlight=False)
    elif steps or minutes:
        # Said once, here: an undeclared planning ceiling is not enforced, and
        # an owner who set --steps could reasonably read it as covering both.
        console.print("planning has no budget — declare one with "
                      "--plan-steps/--plan-minutes", style="dim",
                      markup=False, highlight=False)
    if t.awaiting:
        # asking here is the point of the plan step, and it names what it wants
        console.print("waiting on you to grant:", style="yellow")
        for permission in t.awaiting:
            console.print(f"  {permission}", markup=False, highlight=False)
        console.print(f"grant it with: ai4science sarsi grant {agent_id} {t.id} "
                      f"\"{t.awaiting[0]}\"", style="dim", markup=False, highlight=False)
    elif t.blocked_by:
        console.print(f"not started — {t.blocked_by}", style="yellow",
                      markup=False, highlight=False)


@app.command("tasks", help="Every task this worker holds, and what each is waiting for.")
def tasks(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
          archived: bool = typer.Option(False, "--archived",
                                        help="Show the closed ones instead.")) -> None:
    from ai4science.harness.agents.sarsi import task as tsk

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    rows = tsk.all_of(config, agent, archived=archived)
    closed = 0 if archived else len(tsk.all_of(config, agent, archived=True))
    if not rows:
        console.print(f"{agent_id}: {'nothing archived' if archived else 'no tasks'}")
    else:
        table = Table(title=f"{agent_id} — {'archived' if archived else 'tasks'}",
                      show_lines=False)
        table.add_column("Task", style="cyan")
        table.add_column("Goal")
        table.add_column("State")
        table.add_column("Waiting on")
        for t in rows:
            # a task never looks idle when it is actually blocked: say which
            waiting = ", ".join(t.awaiting) or (t.blocked_by or "—")
            state = t.state
            if t.retries:
                state = f"{state} ({t.retries} retr{'y' if t.retries == 1 else 'ies'})"
            table.add_row(t.id, t.goal, state, waiting)
        console.print(table)
    if closed:
        # counted rather than hidden: archiving must not read as deleting
        console.print(f"{closed} archived — see them with "
                      f"[cyan]sarsi tasks {agent_id} --archived[/cyan]", style="dim")


@app.command("undo", help="Take back the last outward act — when that is possible at all.")
def undo_cmd(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
             show: bool = typer.Option(False, "--show",
                                       help="Say what the last act was, and attempt nothing.")) -> None:
    from ai4science.harness.agents.sarsi import undo as ud

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    act = ud.last(config, agent)
    if act is None:
        console.print(f"{agent_id} has nothing outstanding that left the machine",
                      markup=False, highlight=False)
        return
    console.print(f"last outward act: {act}", markup=False, highlight=False)
    if show:
        return
    try:
        ud.retract(config, agent, retractor=_retractor_for(config, agent, act))
    except ud.NothingToUndo as e:
        console.print(str(e), markup=False, highlight=False)
        return
    except (ud.Irreversible, ud.Failed) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print("retracted — and recorded as an outward act of its own",
                  markup=False, highlight=False)


def _retractor_for(config, agent, act):
    """The call that takes a post down, when this platform has one.

    Returns None rather than raising: `undo` already refuses with the right
    words for a platform nothing can retract, and duplicating that refusal here
    would give the same situation two different explanations.
    """
    from ai4science.harness.agents.sarsi import transmit

    if act.kind != "post":
        return None
    try:
        return transmit.retractor(config, agent, platform=act.destination,
                                  secret=f"{act.destination}.token",
                                  prompt=_terminal_vault_prompt)
    except transmit.NoTransmitter:
        return None


@app.command("questions", help="Escalations waiting on you, across every worker or one.")
def questions_cmd(agent_id: Optional[str] = typer.Option(None, "--agent",
                                                         help="Only this worker.")) -> None:
    from ai4science.harness.agents.sarsi import questions as qst

    config = _load()
    rows = (qst.open_of(config, _worker_or_exit(config, agent_id))
            if agent_id else qst.across(config))
    if not rows:
        console.print("no open questions")
        return
    console.print(f"{len(rows)} open question(s):", style="yellow")
    for q in rows:
        console.print(f"  {q}", markup=False, highlight=False)
        console.print(f"    → sarsi answer {q.agent_id} {q.task_id} "
                      f"\"{q.text}\" \"<your answer>\"", style="dim",
                      markup=False, highlight=False)
    # non-zero so a timer or a shell `if` can act on it without parsing text
    raise typer.Exit(code=1)


@app.command("answer", help="Answer an escalated question — it goes into the session.")
def answer_cmd(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
               task_id: str = typer.Argument(..., help="Task id"),
               question: str = typer.Argument(..., help="The question, as listed"),
               reply: str = typer.Argument(..., help="Your answer")) -> None:
    from ai4science.harness.agents.sarsi import (operator as op,
                                                 questions as qst,
                                                 session as ses)

    config, agent, t = _load_task(agent_id, task_id)
    try:
        # a real pane, so the delivery is CONFIRMED before the question closes:
        # a booting session swallows what is typed at it
        qst.answer(config, agent, t, question, reply, pane=op.TmuxPane())
    except (qst.NotAsked, qst.NoSession, qst.NotDelivered,
            ses.NotDrivable) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=2)
    console.print(f"answered — {t.id} has been told, and the question is closed",
                  markup=False, highlight=False)


@app.command("blast", help="What it wrote, against the paths its plan declared.")
def blast_cmd(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
              task_id: str = typer.Argument(..., help="Task id")) -> None:
    from ai4science.harness.agents.sarsi import blast

    config, agent, t = _load_task(agent_id, task_id)
    got = blast.check(config, agent, t)
    console.print("declared paths:", style="dim")
    for path in got.declared:
        console.print(f"  {path}", markup=False, highlight=False)
    style = "red" if got.escaped else ("dim" if got.confident else "yellow")
    console.print(got.summary, style=style, markup=False, highlight=False)
    for path in got.outside:
        console.print(f"  outside: {path}", style="red", markup=False,
                      highlight=False)
    if got.escaped:
        raise typer.Exit(code=1)


@app.command("decisions", help="What the agent decided without you, and at which rung.")
def decisions(agent_id: Optional[str] = typer.Option(None, "--agent",
                                                     help="Only this worker."),
              ack: bool = typer.Option(False, "--ack",
                                       help="Acknowledge them (needs --agent)."),
              everything: bool = typer.Option(False, "--all",
                                              help="Every one ever, not just the new ones.")) -> None:
    from ai4science.harness.agents.sarsi import decisions as dec

    config = _load()
    if ack and not agent_id:
        # Acknowledging the whole fleet in one keystroke is how a real one gets
        # skimmed past.
        console.print("[red]--ack needs --agent[/red] — acknowledge one worker "
                      "at a time")
        raise typer.Exit(code=2)

    if agent_id:
        agent = _worker_or_exit(config, agent_id)
        got = dec.all_of(config, agent) if everything else dec.since(config, agent)
    else:
        got = dec.across(config)

    console.print(got.summary, markup=False, highlight=False)
    for item in got.items:
        console.print(f"  {item}", markup=False, highlight=False)

    if ack:
        dec.acknowledge(config, _worker_or_exit(config, agent_id))
        console.print("acknowledged — they stay readable with --all", style="dim")


@app.command("spend", help="What it cost: tokens and time, read from the session transcripts.")
def spend(agent_id: Optional[str] = typer.Option(None, "--agent",
                                                 help="Only this worker."),
          task_id: Optional[str] = typer.Option(None, "--task",
                                                help="Only this task (needs --agent).")) -> None:
    from ai4science.harness.agents.sarsi import spend as spd

    config = _load()
    if task_id:
        if not agent_id:
            console.print("[red]--task needs --agent[/red]")
            raise typer.Exit(code=2)
        _c, agent, t = _load_task(agent_id, task_id)
        one = spd.for_task(config, agent, t)
        console.print(f"{agent_id}/{t.id}", style="cyan", markup=False,
                      highlight=False)
        console.print(f"  {one.summary}", markup=False, highlight=False)
        return

    rows = ([spd.for_agent(config, _worker_or_exit(config, agent_id))]
            if agent_id else spd.across(config))
    if not rows:
        console.print("nothing has run yet")
        return
    for row in rows:
        console.print(f"{row.agent_id}  ({row.tasks} task(s))", style="cyan",
                      markup=False, highlight=False)
        console.print(f"  {row.summary}", markup=False, highlight=False)


@app.command("publish", help="Publish one fact to the shared tier every granted agent reads.")
def publish_cmd(agent_id: str = typer.Argument(..., help="Who is saying it"),
                kind: str = typer.Argument(..., help="deadline · entity · decision · outcome · note"),
                text: str = typer.Argument(..., help="The fact, one sentence"),
                about: List[str] = typer.Option(None, "--about",
                                                help="An entity it concerns (repeatable)."),
                source: str = typer.Option("", "--source",
                                           help="Where it came from — mail, a page, the owner."),
                trusted: bool = typer.Option(False, "--trusted",
                                             help="Only if the source itself is trusted.")) -> None:
    from ai4science.harness.agents.sarsi import shared

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    try:
        fact = shared.publish(config, agent, kind=kind, text=text,
                              about=list(about or []), source=source,
                              trusted=trusted)
    except (shared.NotShareable, ValueError) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=2)
    console.print(f"published — {fact['kind']}: {fact['text']}", markup=False,
                  highlight=False)
    console.print("nothing was started by this; whoever plans next will find it",
                  style="dim")


@app.command("shared", help="What has been published, and who may read it.")
def shared_cmd(agent_id: Optional[str] = typer.Option(None, "--agent",
                                                      help="Read as this agent."),
               grant: bool = typer.Option(False, "--grant",
                                          help="Let that agent read the tier."),
               revoke: bool = typer.Option(False, "--revoke",
                                           help="Take the permission back.")) -> None:
    from ai4science.harness.agents.sarsi import shared

    config = _load()
    if (grant or revoke) and not agent_id:
        console.print("[red]--grant and --revoke need --agent[/red]")
        raise typer.Exit(code=2)
    if agent_id:
        agent = _worker_or_exit(config, agent_id)
        if grant:
            shared.grant(config, agent)
            console.print(f"{agent_id} may read the shared tier", markup=False,
                          highlight=False)
        if revoke:
            shared.revoke(config, agent)
            console.print(f"{agent_id} may no longer read it", markup=False,
                          highlight=False)
        if not shared.may_read(config, agent):
            console.print(f"{agent_id} is not granted the shared tier — it is "
                          f"declared, not implied", style="yellow",
                          markup=False, highlight=False)
            console.print(f"  grant it: sarsi shared --agent {agent_id} --grant",
                          style="dim")
            return
        facts = shared.read(config, agent)
    else:
        console.print("readers: " + (", ".join(shared.readers(config)) or "none"),
                      style="dim", markup=False, highlight=False)
        facts = shared._all(config)

    if not facts:
        console.print("nothing has been published")
        return
    for f in facts:
        prov = f.get("provenance") or {}
        trust = "" if prov.get("trusted") else ", not verified"
        console.print(f"  [{f.get('kind')}] {f.get('text')}", markup=False,
                      highlight=False)
        console.print(f"      {f.get('by')}, from {prov.get('source')}{trust}",
                      style="dim", markup=False, highlight=False)


@app.command("board", help="The board as a page — served on this machine only.")
def board_cmd(agent_id: Optional[str] = typer.Argument(None,
                                                       help="Write just this worker's board."),
              host: str = typer.Option("127.0.0.1", "--host",
                                       help="Loopback only; anything else is refused."),
              port: int = typer.Option(0, "--port", help="Port to serve on."),
              write: Optional[str] = typer.Option(None, "--write",
                                                  help="Write the HTML to a file and serve nothing.")) -> None:
    from pathlib import Path

    from ai4science.harness.agents.sarsi import board as bd

    config = _load()
    if write:
        agent = _worker_or_exit(config, agent_id) if agent_id else None
        html = bd.render(config, agent) if agent else bd.index(config)
        target = Path(write).expanduser()
        target.write_text(html)
        console.print(f"wrote {target}", markup=False, highlight=False)
        return

    try:
        server = bd.serve(config, host=host, port=port or bd.DEFAULT_PORT,
                          serve_forever=False)
    except bd.NotLocal as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=2)
    where = f"http://{host}:{server.server_address[1]}/"
    console.print(f"board on {where}  (read-only; nothing here leaves this "
                  f"machine)", markup=False, highlight=False)
    console.print("Ctrl-C to stop", style="dim")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("stopped")


@app.command("who", help="Who should do this? The manager suggests; it creates nothing.")
def who_cmd(demand: str = typer.Argument(..., help="What you want done")) -> None:
    from ai4science.harness.agents.sarsi import triage

    config = _load()
    try:
        got = triage.suggest(config, demand)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    console.print(got.summary, markup=False, highlight=False)
    if len(got.candidates) > 1:
        console.print("\nothers considered:", style="dim")
        for c in got.candidates[1:4]:
            console.print(f"  {c.agent_id} — {c.why}", style="dim",
                          markup=False, highlight=False)


@app.command("digest", help="One read across what an agent did — instead of many.")
def digest_cmd(agent_id: Optional[str] = typer.Option(None, "--agent",
                                                      help="Only this worker."),
               deliver: bool = typer.Option(False, "--deliver",
                                            help="Mark it read (needs --agent).")) -> None:
    from ai4science.harness.agents.sarsi import digest as dg

    config = _load()
    if deliver and not agent_id:
        console.print("[red]--deliver needs --agent[/red] — one agent at a time")
        raise typer.Exit(code=2)

    if agent_id:
        agent = _worker_or_exit(config, agent_id)
        got = dg.deliver(config, agent) if deliver else dg.compile(config, agent)
        rows = [got]
    else:
        rows = dg.across(config)

    for row in rows:
        console.print(row.text, markup=False, highlight=False)
    if deliver:
        console.print("delivered — the next one starts from here", style="dim")


@app.command("rules", help="House rules for this machine — told to every session.")
def rules_cmd(agent_id: str = typer.Argument(..., help="Agent id, e.g. sarsi-worker"),
              add: Optional[str] = typer.Option(None, "--add",
                                                help="Add a rule."),
              remove: Optional[str] = typer.Option(None, "--remove",
                                                   help="Remove one, exactly as written."),
              sign: bool = typer.Option(False, "--sign",
                                        help="Adopt the rule this agent proposed."),
              discard: bool = typer.Option(False, "--discard",
                                           help="Refuse the proposal.")) -> None:
    from ai4science.harness.agents.sarsi import rules as rl

    config = _load()
    agent = config.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]no agent {agent_id!r}[/red] — known: "
                      f"{', '.join(sorted(config.agents))}")
        raise typer.Exit(code=2)

    try:
        if add:
            rl.add(config, agent, add)
        if remove:
            rl.remove(config, agent, remove)
        if sign:
            adopted = rl.sign(config, agent, by_owner=True)
            console.print(f"adopted: {adopted['rule']}" if adopted
                          else "nothing was pending", markup=False,
                          highlight=False)
        if discard:
            rl.discard(config, agent)
            console.print("proposal discarded", markup=False, highlight=False)
    except (rl.LooksLikeASecret, rl.TooMany, rl.NoSuchRule, ValueError) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=2)

    held = rl.pending(config, agent)
    if held:
        console.print(f"{agent_id} proposes: {held['rule']}", style="yellow",
                      markup=False, highlight=False)
        console.print(f"  because {held.get('because', '')}", style="dim",
                      markup=False, highlight=False)
        console.print(f"  adopt it: sarsi rules {agent_id} --sign", style="dim")

    current = rl.read(config, agent)
    if not current:
        console.print(f"{agent_id}: no house rules")
        return
    console.print(f"{agent_id} — {len(current)} house rule(s) for this machine:",
                  markup=False, highlight=False)
    for rule in current:
        console.print(f"  - {rule}", markup=False, highlight=False)
    console.print(f"every session this agent starts is told them "
                  f"({rl.path(agent)})", style="dim", markup=False,
                  highlight=False)


@app.command("handoff", help="HANDOFF.md for a task, or hand finished work to another worker.")
def handoff_cmd(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
                task_id: Optional[str] = typer.Argument(None, help="Task id"),
                to: Optional[str] = typer.Option(None, "--to",
                                                 help="Hand it to this worker."),
                goal: Optional[str] = typer.Option(None, "--goal",
                                                   help="What they should do."),
                because: Optional[str] = typer.Option(None, "--because",
                                                      help="Why this is the next step."),
                accept: bool = typer.Option(False, "--accept",
                                            help="Accept the handoff waiting for this worker."),
                decline: bool = typer.Option(False, "--decline",
                                             help="Refuse it.")) -> None:
    from ai4science.harness.agents.sarsi import handoff as ho, relay

    config = _load()

    # ── the owner acting on one that is waiting ───────────────────────
    if accept or decline or (task_id is None and to is None):
        agent = _worker_or_exit(config, agent_id)
        if decline:
            relay.decline(config, agent)
            console.print("declined — nothing was created", markup=False,
                          highlight=False)
            return
        if accept:
            try:
                made = relay.accept(config, agent, by_owner=True)
            except relay.OwnerMustAccept as e:
                console.print(str(e), style="yellow", markup=False,
                              highlight=False)
                raise typer.Exit(code=2)
            if made is None:
                console.print(f"nothing is waiting for {agent_id}")
                return
            console.print(f"{agent_id} holds {made.id} — {made.goal}",
                          markup=False, highlight=False)
            console.print(f"  it cites {made.depends_on[0]}", style="dim",
                          markup=False, highlight=False)
            return
        held = relay.pending(config, agent)
        if held is None:
            console.print(f"nothing is waiting for {agent_id}")
            return
        console.print(f"{held['from_agent']} finished {held['from_task']} "
                      f"(\"{held['from_goal']}\") and asks {agent_id} to:",
                      markup=False, highlight=False)
        console.print(f"  {held['goal']}", markup=False, highlight=False)
        console.print(f"  because {held['because']}", style="dim",
                      markup=False, highlight=False)
        console.print(f"  accept it: sarsi handoff {agent_id} --accept",
                      style="dim")
        return

    # ── handing finished work on ──────────────────────────────────────
    if to:
        config, agent, t = _load_task(agent_id, task_id)
        if not (goal and because):
            console.print("[red]--to needs --goal and --because[/red] — the "
                          "owner is deciding, and 'it suggested it' is not a "
                          "reason")
            raise typer.Exit(code=2)
        try:
            relay.propose(config, agent, t, to=to, goal=goal, because=because)
        except (relay.NotFinished, relay.NotAWorker, KeyError, ValueError) as e:
            console.print(str(e).strip("\""), style="yellow", markup=False,
                          highlight=False)
            raise typer.Exit(code=2)
        console.print(f"proposed to {to} — nothing was created; they see it in "
                      f"`sarsi attention --agent {to}`", markup=False,
                      highlight=False)
        return

    # ── the per-session handoff file ──────────────────────────────────
    config, agent, t = _load_task(agent_id, task_id)
    path = ho.write(config, agent, t)
    console.print(path.read_text(), markup=False, highlight=False)
    console.print(f"\nwritten to {path}", style="dim", markup=False,
                  highlight=False)


@app.command("why", help="Why is it doing this: the goal, the criteria, and the last verdict.")
def why(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
        task_id: str = typer.Argument(..., help="Task id")) -> None:
    from ai4science.harness.agents.sarsi import why as wy
    config, agent, t = _load_task(agent_id, task_id)
    console.print(wy.explain(config, agent, t), markup=False, highlight=False)


@app.command("attention", help="What is waiting on YOU — across every worker, or one.")
def attention(agent_id: Optional[str] = typer.Option(None, "--agent",
                                                     help="Only this worker.")) -> None:
    from ai4science.harness.agents.sarsi import attention as att, operator as op

    config = _load()
    pane = op.TmuxPane()
    if agent_id:
        agent = _worker_or_exit(config, agent_id)
        found = att.needs(config, agent, pane=pane, live=None)
        rows = [att.Item(kind=i.kind, task_id=i.task_id, detail=i.detail,
                         agent_id=agent.id, action=i.action) for i in found.items]
        found = att.Attention(items=rows)
    else:
        found = att.across(config, pane=pane)

    console.print(found.summary, markup=False, highlight=False)
    for item in found.items:
        console.print(f"  [{item.kind}] {item.agent_id}/{item.task_id}",
                      style="yellow", markup=False, highlight=False)
        console.print(f"      {item.detail}", markup=False, highlight=False)
        if item.action:
            console.print(f"      → {item.action}", style="dim",
                          markup=False, highlight=False)
    if found.items:
        # a non-zero exit so a timer or a shell `if` can act on it without
        # parsing the text
        raise typer.Exit(code=1)


@app.command("enter", help="Step into a worker: its current task, or the question it wants answered.")
def enter(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker")) -> None:
    from ai4science.harness.agents.sarsi import entry

    config = _load()
    agent = config.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]no agent {agent_id!r}[/red] — known: "
                      f"{', '.join(sorted(config.agents))}")
        raise typer.Exit(code=2)
    console.print(entry.enter(config, agent, surface="cli"),
                  markup=False, highlight=False)


@app.command("stop", help="Stop a task and close its session. Resumable — the plan survives.")
def stop(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
         task_id: str = typer.Argument(..., help="Task id")) -> None:
    from ai4science.harness.agents.sarsi import session as ses
    config, agent, t = _load_task(agent_id, task_id)
    t = ses.stop(config, agent, t)
    console.print(f"{t.id} stopped — its slot is free", markup=False, highlight=False)
    console.print(f"pick it up again: sarsi run {agent_id} {t.id}", style="dim")


@app.command("archive", help="Close a task for good: the record is kept, the slot is freed.")
def archive(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
            task_id: str = typer.Argument(..., help="Task id")) -> None:
    from ai4science.harness.agents.sarsi import session as ses
    config, agent, t = _load_task(agent_id, task_id)
    t = ses.stop(config, agent, t, archive=True)
    console.print(f"{t.id} archived — off the board, and kept",
                  markup=False, highlight=False)
    console.print(f"read it any time: sarsi plan {agent_id} {t.id}", style="dim")


@app.command("reopen", help="Put an archived task back on the board, stopped.")
def reopen(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
           task_id: str = typer.Argument(..., help="Task id")) -> None:
    from ai4science.harness.agents.sarsi import task as tsk
    config, agent, t = _load_task(agent_id, task_id)
    if t.state != tsk.ARCHIVED:
        console.print(f"[yellow]{t.id} is not archived — it is {t.state}[/yellow]")
        raise typer.Exit(code=1)
    t = tsk.reopen(config, agent, t)
    console.print(f"{t.id} is back on the board, stopped",
                  markup=False, highlight=False)


@app.command("goal", help="Change a task's goal — the plan is re-drafted to follow it.")
def goal(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
         task_id: str = typer.Argument(..., help="Task id"),
         text: str = typer.Argument(..., help="The new goal — one sentence")) -> None:
    from ai4science.harness.agents.sarsi import chat as sarsi_chat
    config, agent, t = _load_task(agent_id, task_id)
    out = sarsi_chat.handle(config, agent, f"/goal {t.id} {text}", surface="cli")
    console.print(out, markup=False, highlight=False)


@app.command("retry", help="Hand a FAILed task back to its session with the verifier's reason.")
def retry(agent_id: str = typer.Argument(..., help="Worker id, e.g. sarsi-worker"),
          task_id: str = typer.Argument(..., help="Task id")) -> None:
    from ai4science.harness.agents.sarsi import retry as rty, session as ses
    config, agent, t = _load_task(agent_id, task_id)
    try:
        t = rty.retry(config, agent, t)
    except (rty.NothingToRetry, rty.Exhausted, ses.NotDrivable,
            ses.NoSession) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print(f"{t.id} handed back — attempt {t.retries} of {rty.MAX_RETRIES}",
                  markup=False, highlight=False)
    console.print(f"watch it: sarsi supervise {agent_id} {t.id}", style="dim")


def _load_task(agent_id: str, task_id: str):
    """(config, agent, task) for the lifecycle verbs. `_task_or_exit` below
    takes an already-loaded config; this is the one-call form."""
    config = _load()
    agent = _worker_or_exit(config, agent_id)
    return config, agent, _task_or_exit(config, agent, task_id)


@app.command("forecast", help="Say how likely this task is to be VERIFIED — before it is.")
def forecast_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
                 task_id: str = typer.Argument(..., help="Task id, e.g. tsk_…"),
                 p: float = typer.Argument(..., help="Probability in [0, 1]"),
                 why: str = typer.Option("", "--why",
                                         help="What that number rests on.")) -> None:
    """A forecast is only evidence if it precedes the outcome, so this refuses
    once the task has been judged rather than recording a number that would
    score perfectly and mean nothing."""
    from ai4science.harness.agents.sarsi import forecast as _fc

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    try:
        t = _fc.record(config, agent, t, p, why=why)
    except (_fc.TooLate, ValueError) as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=2)
    console.print(f"{t.id} — forecast {p:.0%} recorded before the verdict",
                  markup=False, highlight=False)
    cal = _fc.calibration(config, agent)
    if cal:
        console.print(f"  so far: {_fc.render(cal)}", style="dim",
                      markup=False, highlight=False)


@app.command("plan", help="Show one task's plan — or write it yourself with --set-from.")
def plan_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
             task_id: str = typer.Argument(..., help="Task id, e.g. tsk_…"),
             set_from: str = typer.Option(
                 "", "--set-from",
                 help="A markdown plan file YOU wrote. It becomes the standard: "
                      "agreed on arrival, and a session may not rewrite its "
                      "criteria. Its permissions still need granting.")) -> None:
    from ai4science.harness.agents.sarsi import task as tsk

    config = _load()
    if set_from:
        # The owner's half of "here is the plan, follow it". Refused here rather
        # than at run time, because this text becomes the standard a verdict is
        # measured against.
        from ai4science.harness.agents.sarsi import plan as _pl
        agent = _worker_or_exit(config, agent_id)
        t = _task_or_exit(config, agent, task_id)
        try:
            text = pathlib.Path(set_from).read_text()
        except OSError as e:
            console.print(f"could not read {set_from}: {e}", style="red",
                          markup=False, highlight=False)
            raise typer.Exit(code=2)
        try:
            t = tsk.set_owner_plan(config, agent, t, text)
        except _pl.BadPlan as e:
            console.print(f"that file is not a plan: {e}", style="red",
                          markup=False, highlight=False)
            raise typer.Exit(code=2)
        console.print(f"{t.id} now follows the plan you wrote — "
                      f"{t.plan_version}.md, agreed.", markup=False,
                      highlight=False)
        if t.awaiting:
            console.print("it still declares permissions to grant:",
                          markup=False, highlight=False)
            for perm in t.awaiting:
                console.print(f"  sarsi grant {agent.id} {t.id} \"{perm}\"",
                              style="dim", markup=False, highlight=False)
        return

    agent = _worker_or_exit(config, agent_id)
    t = tsk.get(config, agent, task_id)
    if t is None:
        console.print(f"[red]no task {task_id!r} for {agent_id}[/red]")
        raise typer.Exit(code=2)
    plan = tsk.read_plan_or_none(config, agent, t)
    if plan is None and t.plan_version:
        # Unreadable, not absent. Show the FILE: the owner is the one who has
        # to fix it, and a rendered summary they cannot get is worth less
        # than the broken text they can edit.
        path = tsk.dir_of(agent, t.id) / f"{t.plan_version}.md"
        if path.exists():
            console.print(f"{t.plan_version}.md cannot be parsed — a phase is "
                          f"missing its `Verified when:` line. The file as it "
                          f"stands:", style="yellow", markup=False,
                          highlight=False)
            console.print(path.read_text(), markup=False, highlight=False)
            raise typer.Exit(code=1)
    if plan is None:
        console.print(f"{task_id} has no plan yet")
        raise typer.Exit(code=1)
    console.print(plan.render(), markup=False, highlight=False)


@app.command("grant", help="Grant one permission a task's plan declared.")
def grant_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
              task_id: str = typer.Argument(..., help="Task id"),
              permission: str = typer.Argument(..., help="Exactly the permission the plan named")) -> None:
    from ai4science.harness.agents.sarsi import task as tsk

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = tsk.get(config, agent, task_id)
    if t is None:
        console.print(f"[red]no task {task_id!r} for {agent_id}[/red]")
        raise typer.Exit(code=2)
    before = list(t.awaiting)
    t = tsk.start(config, agent, tsk.grant(config, agent, t, permission))
    if permission not in before:
        # a grant answers the permission it names, and no other
        console.print(f"granted, but {permission!r} was not one this task asked "
                      f"for; still waiting on: {', '.join(t.awaiting) or 'nothing'}",
                      style="yellow", markup=False, highlight=False)
        return
    console.print(f"{t.id} — {t.state}", markup=False, highlight=False)


def _worker_or_exit(config: reg.Config, agent_id: str):
    agent = config.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]no agent {agent_id!r}[/red] — known: "
                      f"{', '.join(sorted(config.agents))}")
        raise typer.Exit(code=2)
    return agent


@app.command("run", help="Hand a task's plan to its backend — sarsi-claude or "
                         "sarsi-pwm, whichever the task carries — and start "
                         "the governed session.")
def run_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
            task_id: str = typer.Argument(..., help="Task id"),
            deny_secrets: bool = typer.Option(False, "--deny-secrets",
                                              help="Answer every vault prompt with no (a dry check).")) -> None:
    from ai4science.harness.agents.sarsi import session as ses, task as tsk, worker

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    prompt = (lambda **kw: "no") if deny_secrets else _terminal_vault_prompt
    try:
        t = ses.assign(config, agent, t, vault_prompt=prompt)
    except worker.NotAWorker as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=2)
    except (ses.NotReady, ses.CouldNotRelease) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    except ses.CouldNotStart as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=1)
    name = (t.session or {}).get("name", "?")
    console.print(f"{t.id} — {t.state} in session {name}",
                  markup=False, highlight=False)
    if t.state == "planning":
        console.print("it is drafting the plan from my initial one; "
                      "`sarsi supervise` collects it and shows what it needs",
                      style="dim", markup=False, highlight=False)
    console.print(f"take the wheel yourself: tmux attach -t {name}   "
                  f"(Ctrl-b d hands it back)", style="dim",
                  markup=False, highlight=False)


@app.command("send", help="Ask to let one act leave the machine. Drafting is not sending.")
def send_cmd(agent_id: str = typer.Argument(..., help="Agent id"),
             kind: str = typer.Option("mail", "--kind", help="mail | post | submit | pay | …"),
             to: str = typer.Option(..., "--to", help="Recipient or destination"),
             body: str = typer.Option(..., "--body", help="Exactly what would go out"),
             subject: str = typer.Option("", "--subject",
                                         help="Transmitted too, so you are shown it"),
             task_id: str = typer.Option("", "--task", help="The task it belongs to"),
             undo_cost: str = typer.Option("", "--undo-cost",
                                           help="What undoing costs, if known"),
             undo_until: str = typer.Option("", "--undo-until",
                                            help="Until when undoing is free"),
             dry_run: bool = typer.Option(False, "--dry-run",
                                          help="Go through the gate, then report instead of sending.")) -> None:
    from ai4science.harness.agents.sarsi import outward

    config = _load()
    agent = config.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]no agent {agent_id!r}[/red]")
        raise typer.Exit(code=2)

    reversibility = ({"cost": undo_cost, "until": undo_until or None}
                     if undo_cost else None)
    act = outward.Act(agent_id=agent_id, kind=kind, destination=to, body=body,
                      subject=subject, task_id=task_id,
                      reversibility=reversibility)

    def approve(*, act, shown, reversibility):
        # the owner reads the actual words: OWN is a composition step, not a
        # rubber stamp, and this is where a bad draft is caught
        console.print("\n" + shown, markup=False, highlight=False)
        console.print(reversibility, style="yellow", markup=False, highlight=False)
        return typer.confirm("send this?", default=False)

    from ai4science.harness.agents.sarsi import transmit as tx

    sent: list = []
    # Authority is answered before mechanics: an act this agent must abstain on
    # is refused for that reason, not for a missing transmitter. Otherwise the
    # answer to "abraham, pay the shop" would be a wiring complaint.
    will_abstain = act.kind in outward.RESERVED and not agent.standing_grants
    if dry_run or will_abstain:
        sender = tx.dry_run(sent)
    else:
        try:
            # resolved BEFORE the gate: approving something with nowhere to go
            # spends the owner's attention and records an approval for an act
            # that never happened
            sender = _real_transmitter(config, agent, act)
        except (tx.NoTransmitter, _MissingSettings) as e:
            console.print(str(e), style="yellow", markup=False, highlight=False)
            raise typer.Exit(code=1)

    try:
        outcome = outward.request(config, agent, act, approve=approve, transmit=sender)
    except outward.NotWhatWasApproved as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=2)
    except tx.TooLongToPost as e:
        # refused, never truncated
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    except tx.TransmitFailed as e:
        # recorded as failed, not sent: a message nobody received is not sent
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=1)

    if outcome.abstained:
        console.print(outcome.reason, style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    if not outcome.approved:
        # a refusal is an outcome, not an error — but the shell still learns it
        console.print(f"not sent — {outcome.reason}", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print(f"would have sent {len(sent[0]['body'])} characters to {to}"
                  if dry_run else f"sent to {to}",
                  markup=False, highlight=False)


class _MissingSettings(Exception):
    """The transmitter exists but this machine has not been told how to reach it."""


def _real_transmitter(config: reg.Config, agent, act):
    """Build the transmitter for this act, or say what is missing.

    Mail settings live in the registry beside the agent; the PASSWORD does not —
    it is a vault secret, asked for at send time.
    """
    import os

    from ai4science.harness.agents.sarsi import transmit as tx, vault

    if act.kind == "post":
        # the destination IS the platform; its token is a vault secret named
        # after it, so one agent can hold several without them blurring
        platform = (act.destination or "").strip().lower()
        if platform not in tx.PLATFORMS:
            # named before the token is looked for: "no mastodon.token" invites
            # you to go and find a token for a platform never supported
            raise tx.NoTransmitter(
                f"no transmitter for {platform!r} — known platforms: "
                f"{', '.join(sorted(tx.PLATFORMS))}")
        secret = os.environ.get("SARSI_POST_SECRET", f"{platform}.token")
        if secret not in vault.names(config):
            raise _MissingSettings(
                f"posting to {platform} is wired, but this machine holds no "
                f"{secret} in the vault: ai4science sarsi vault put {secret}")
        return tx.post(config, agent, platform=platform, secret=secret,
                       prompt=_terminal_vault_prompt)
    if act.kind == "submit":
        raise tx.NoTransmitter(
            "submitting is wired but is never built from a --body: use "
            "`ai4science sarsi submit <agent> <form.json>`, so every field and "
            "value is shown to you rather than a paragraph about them")
    if act.kind != "mail":
        raise tx.NoTransmitter(
            f"nothing is wired to {act.kind} — the gate would approve this and "
            f"then have nowhere to send it")
    host = os.environ.get("SARSI_SMTP_HOST")
    user = os.environ.get("SARSI_SMTP_USER")
    port = int(os.environ.get("SARSI_SMTP_PORT", "587"))
    secret = os.environ.get("SARSI_SMTP_SECRET", "mail.smtp")
    if not host or not user:
        raise _MissingSettings(
            "mail is wired but this machine has no SMTP settings: set "
            "SARSI_SMTP_HOST and SARSI_SMTP_USER, and hold the password in the "
            "vault as " + secret)
    return tx.smtp_mail(config, agent, host=host, port=port, user=user,
                        secret=secret, prompt=_terminal_vault_prompt)


vault_app = typer.Typer(help="The vault: secrets never leave this machine.",
                        no_args_is_help=True)
app.add_typer(vault_app, name="vault")


@vault_app.command("list", help="The names of the secrets held — never their values.")
def vault_list() -> None:
    from ai4science.harness.agents.sarsi import vault

    config = _load()
    names = vault.names(config)
    if not names:
        console.print("the vault is empty")
        return
    # names only: the only interface to a value is the question
    for name in names:
        console.print(f"  {name}", markup=False, highlight=False)


@vault_app.command("put", help="Add or replace one secret. Its value is never echoed.")
def vault_put(name: str = typer.Argument(..., help="e.g. mail.read"),
              value: str = typer.Option(..., "--value", prompt=True, hide_input=True,
                                        help="The secret itself.")) -> None:
    from ai4science.harness.agents.sarsi import vault

    vault.put(_load(), name, value)
    console.print(f"held: {name}", markup=False, highlight=False)


@vault_app.command("policy", help="Write a standing policy. Permitting money needs limit + counterparty + rate.")
def vault_policy(agent_id: str = typer.Argument(..., help="Agent the policy is for"),
                 secret: str = typer.Argument(..., help="Secret it covers"),
                 act: str = typer.Argument(..., help="read | send | pay | post | …"),
                 allow: bool = typer.Option(False, "--allow", help="ALLOW (default is DENY)"),
                 amount: Optional[float] = typer.Option(None, "--amount"),
                 currency: str = typer.Option("", "--currency"),
                 counterparty: str = typer.Option("", "--counterparty",
                                                  help="A payee CLASS, e.g. grocery. Never a wildcard."),
                 uses: Optional[int] = typer.Option(None, "--uses"),
                 per: str = typer.Option("", "--per", help="day | week | month")) -> None:
    from ai4science.harness.agents.sarsi import vault

    config = _load()
    try:
        vault.write_policy(
            config, agent_id=agent_id, secret=secret, act=act,
            decision=vault.ALLOW if allow else vault.DENY,
            limit={"amount": amount, "currency": currency} if amount is not None else None,
            counterparty={"class": counterparty} if counterparty else None,
            rate={"uses": uses, "per": per} if uses is not None else None)
    except vault.PolicyRefused as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=2)
    console.print(f"policy written: {agent_id} {act} {secret} — "
                  f"{'ALLOW' if allow else 'DENY'}", markup=False, highlight=False)


@app.command("operate", help="Nudge a session past the two things that stall it: a gate, and a stranded prompt.")
def operate_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
                task_id: str = typer.Argument(..., help="Task id"),
                passes: int = typer.Option(20, "--passes",
                                           help="How many supervision passes."),
                interval: float = typer.Option(3.0, "--interval",
                                               help="Seconds between passes.")) -> None:
    from ai4science.harness.agents.sarsi import operator as op

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    actions = op.run(config, agent, t, pane=op.TmuxPane(), passes=passes,
                     interval=interval)
    for action in actions:
        # 'abstained' is the interesting one: a gate it would not guess at
        console.print(f"  {action.kind}"
                      + (f" — {action.detail}" if action.detail else ""),
                      markup=False, highlight=False)
    if any(a.kind == "abstained" for a in actions):
        console.print("a gate is waiting for you: tmux attach -t "
                      f"{(t.session or {}).get('name', '?')}", style="yellow",
                      markup=False, highlight=False)


@app.command("submit", help="Submit an application form — every field shown, and it cannot be undone.")
def submit_cmd(agent_id: str = typer.Argument(..., help="Worker id, e.g. jobs"),
               form_path: str = typer.Argument(..., help="A JSON form: url + fields"),
               dry_run: bool = typer.Option(False, "--dry-run",
                                            help="Go through the gate, then do not submit.")) -> None:
    import json as _json
    from pathlib import Path

    from ai4science.harness.agents.sarsi import outward, transmit as tx

    config = _load()
    agent = config.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]no agent {agent_id!r}[/red]")
        raise typer.Exit(code=2)
    try:
        raw = _json.loads(Path(form_path).read_text())
    except Exception as e:
        console.print(f"[red]could not read {form_path}: {e}[/red]")
        raise typer.Exit(code=2)

    form = tx.Form(url=raw.get("url", ""),
                   fields=tuple(tx.Field(name=f.get("name", ""),
                                         value=str(f.get("value", "")),
                                         required=bool(f.get("required")),
                                         # supplied means the OWNER stated it
                                         supplied=bool(f.get("supplied")))
                                for f in raw.get("fields", [])))
    act = tx.submission(agent, form)
    driver = tx.dry_run([]) if dry_run else tx.playwright_driver()
    sender = (tx.dry_run([]) if dry_run
              else tx.submit_form(config, agent, form, driver=driver))

    def approve(*, act, shown, reversibility):
        console.print("\n" + shown, markup=False, highlight=False)
        console.print(reversibility, style="bold yellow", markup=False, highlight=False)
        return typer.confirm("submit this?", default=False)

    try:
        outcome = outward.request(config, agent, act, approve=approve, transmit=sender)
    except (tx.AskTheOwnerFirst, tx.IncompleteForm) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    except outward.NotWhatWasApproved as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=2)
    except (tx.NoTransmitter, tx.TransmitFailed) as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=1)

    if outcome.abstained:
        console.print(outcome.reason, style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    if not outcome.approved:
        console.print(f"not submitted — {outcome.reason}", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print("would have submitted" if dry_run else f"submitted to {form.url}",
                  markup=False, highlight=False)


@app.command("supervise", help="Drive a task to a verified result: verify, answer, submit, steer.")
def supervise_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
                  task_id: str = typer.Argument(..., help="Task id"),
                  passes: int = typer.Option(12, "--passes",
                                             help="How many supervision passes."),
                  interval: float = typer.Option(20.0, "--interval",
                                                 help="Seconds between passes."),
                  no_verify: bool = typer.Option(False, "--no-verify",
                                                 help="Do not verify; unstick and steer only."),
                  no_steer: bool = typer.Option(False, "--no-steer",
                                                help="Do not compose instructions; unstick only."),
                  accept_seed: bool = typer.Option(
                      False, "--accept-seed",
                      help="Take the worker's own seed plan when the session "
                           "never improved it. Deliberate: collecting a seed "
                           "the session ignored launders the worker's draft "
                           "as the session's work.")) -> None:
    from ai4science.harness.agents.sarsi import (composer as cp, operator as op,
                                                 verifier as vf)

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    engine = vf.chosen_engine()
    # What the task said BEFORE this run, so the closing line can say whether
    # the verdict it prints is this run's or one it inherited.
    was = dict(t.verdict or {})
    actions = op.run(config, agent, t, pane=op.TmuxPane(),
                     verifier=None if no_verify else vf.default_verifier(),
                     model=None if no_steer else cp.claude_model(),
                     engine=engine, passes=passes, interval=interval,
                     accept_seed=accept_seed)
    for action in actions:
        console.print(f"  {action.kind}"
                      + (f" — {action.detail}" if action.detail else ""),
                      markup=False, highlight=False)
    final = _task_or_exit(config, agent, task_id)
    from ai4science.harness.agents.sarsi import session as ses
    console.print("\n" + ses.answer(config, agent, final,
                                   fresh=dict(final.verdict or {}) != was),
                  markup=False, highlight=False)
    if any(a.kind == "abstained" for a in actions):
        console.print("a gate is waiting for you: tmux attach -t "
                      f"{(final.session or {}).get('name', '?')}", style="yellow",
                      markup=False, highlight=False)


@app.command("release", help="Let a planned, granted task start working its plan.")
def release_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
                task_id: str = typer.Argument(..., help="Task id")) -> None:
    from ai4science.harness.agents.sarsi import session as ses

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    try:
        t = ses.release(config, agent, t)
    except ses.NotReady as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print(f"{t.id} — {t.state}", markup=False, highlight=False)


@app.command("guide", help="Steer a session by hand — your word goes in ahead of the worker's.")
def guide_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
              task_id: str = typer.Argument(..., help="Task id"),
              instruction: str = typer.Argument(..., help="What to say to the session")) -> None:
    from ai4science.harness.agents.sarsi import session as ses

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    # by_owner: this is you, so it goes in even while you hold the wheel
    try:
        ses.guide(config, agent, t, instruction, by_owner=True)
    except (ses.NoSession, ses.NotDrivable, ses.OwnerHasTheWheel) as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=2)
    console.print(f"sent to {(t.session or {}).get('name', '?')}",
                  markup=False, highlight=False)


@app.command("tools", help="What this machine has, as this agent sees it — and declare what it cannot check.")
def tools_cmd(agent_id: str = typer.Argument(..., help="Agent id, e.g. sarsi-worker"),
              declare: Optional[str] = typer.Option(None, "--declare",
                                    help="Tell CAP a tool it cannot check IS here."),
              note: str = typer.Option("", "--note",
                                    help="Why, or which build — shown beside the declaration."),
              undeclare: Optional[str] = typer.Option(None, "--undeclare",
                                    help="Withdraw a declaration.")) -> None:
    """`CAP` had no CLI at all, so what an agent believed about this machine was
    only visible from inside the code — and a tool it has no probe for could not
    be declared present by anybody.
    """
    from ai4science.harness.agents.sarsi import capability as cap

    config = _load()
    agent = config.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]no agent {agent_id!r}[/red] — known: "
                      f"{', '.join(sorted(config.agents))}")
        raise typer.Exit(code=2)

    if declare:
        cap.declare(config, agent, declare, note=note)
        console.print(f"{agent.id}: {declare} is declared present — the owner's "
                      f"word, not a probe", markup=False, highlight=False)
    if undeclare:
        cap.undeclare(config, agent, undeclare)
        console.print(f"{agent.id}: {undeclare} is no longer declared",
                      markup=False, highlight=False)

    inv = cap.inventory(config, agent)
    if not inv:
        console.print(f"{agent.id} declares no tools", markup=False,
                      highlight=False)
        return
    for name, p in inv.items():
        mark = "yes" if p.present else "no "
        console.print(f"  {mark}  {name:<12} {p.how}", markup=False,
                      highlight=False)


@app.command("adopt", help="Take the plan FILE as the standard, after editing it by hand.")
def adopt_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
              task_id: str = typer.Argument(..., help="Task id, e.g. tsk_…")) -> None:
    """The owner's half of the plan-file question.

    `check` refuses a task whose `plan0.md` no longer matches the criteria it
    was attached with, and refuses rather than resolving it, because that file
    sits in the session's own working directory — taking it automatically would
    let the agent being judged restate the question and drop the verdict that
    failed it. So adopting is an act, and only the owner performs it.
    """
    from ai4science.harness.agents.sarsi import task as _t

    config, agent, t = _load_task(agent_id, task_id)
    moved = _t.adopt_criteria(agent, t)
    if not moved:
        console.print(f"{t.id} already judges what {t.plan_version}.md says — "
                      f"nothing to adopt.", markup=False, highlight=False)
        return
    which = ", ".join(str(i + 1) for i in moved)
    console.print(f"{t.id} now judges what {t.plan_version}.md says. Phase "
                  f"{which} changed, so any verdict those phases had is "
                  f"cleared — they were judged against a standard that no "
                  f"longer exists.", markup=False, highlight=False)
    for i, criterion in enumerate(t.criteria or [], start=1):
        console.print(f"  {i}. {criterion}", style="dim", markup=False,
                      highlight=False)


@app.command("check", help="Ask the independent verifier whether this task's goal is met.")
def check_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
              task_id: str = typer.Argument(..., help="Task id"),
              evidence: str = typer.Option("", "--evidence",
                                           help="The visible evidence to judge."),
              no_model: bool = typer.Option(False, "--no-model",
                                            help="Do not call a model; report that no verifier was available."),
              engine: str = typer.Option("", "--engine",
                                         help="Which engine judged (recorded with the verdict)."),
              phase: Optional[int] = typer.Option(None, "--phase",
                                                  help="Judge ONE phase (1-based) against its own criterion.")) -> None:
    from ai4science.harness.agents.sarsi import session as ses, verifier as vf

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    judge = vf.unavailable("--no-model was given") if no_model else vf.default_verifier()
    if not evidence.strip():
        # Gather it rather than answering UNVERIFIED for want of a paste. A live
        # run wrote its artefacts correctly and was recorded "nothing visible
        # was supplied" purely because nobody had typed a listing in.
        from ai4science.harness.agents.sarsi import evidence as evd, task as _t
        evidence = evd.gather(_t.evidence_roots(agent, t), t.criteria or [])
    try:
        t = ses.verify(config, agent, t, verifier=judge, evidence=evidence,
                       engine=engine or None,
                       phase=None if phase is None else phase - 1)
    except IndexError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    if phase is not None:
        console.print(f"phase {phase} of {len(t.criteria or [])}",
                      style="dim", markup=False, highlight=False)
    verdict = t.verdict or {}
    console.print(f"{verdict.get('state', '?')}: {verdict.get('why', '')}",
                  markup=False, highlight=False)
    console.print(ses.answer(config, agent, t), markup=False, highlight=False)


def _terminal_vault_prompt(*, secret: str, purpose: str, agent: str, act: str):
    """Stage 2, at the terminal: name the secret and what it is for, then ask.

    Approving here approves **this one use**. Nothing about it becomes standing:
    that is `sarsi vault policy`, and it is deliberately a separate act.
    """
    console.print(f"\n{agent} wants to {act} the secret {secret}", style="yellow",
                  markup=False, highlight=False)
    console.print(f"  for: {purpose}", markup=False, highlight=False)
    console.print("  (this one use only)", style="dim")
    return typer.confirm("  allow?", default=False)


def _task_or_exit(config: reg.Config, agent, task_id: str):
    from ai4science.harness.agents.sarsi import task as tsk

    t = tsk.get(config, agent, task_id)
    if t is None:
        console.print(f"[red]no task {task_id!r} for {agent.id}[/red]")
        raise typer.Exit(code=2)
    return t


@app.command("gateway", help="Run the local daemon: poll every agent's bot and route what arrives.")
def gateway_cmd(passes: Optional[int] = typer.Option(None, "--passes",
                                                     help="Stop after N polls (default: run forever)."),
                interval: float = typer.Option(2.0, "--interval",
                                               help="Seconds between polls.")) -> None:
    from ai4science.harness.agents.sarsi import admin as _admin, gateway as gw

    config = _load()
    reachable = [r["id"] for r in _admin.agent_rows(config) if r["telegram"] == "configured"]
    if not reachable:
        console.print("[red]no agent has a bot token[/red] — nothing to poll.\n"
                      "set one with: [cyan]ai4science sarsi set-token <agent> <token>[/cyan]")
        raise typer.Exit(code=2)
    console.print(f"polling {len(reachable)} bot(s): {', '.join(reachable)}")
    try:
        gw.Gateway(config).run(interval=interval, passes=passes)
    except KeyboardInterrupt:
        console.print("stopped")


@app.command("ceiling", help="Set the auto level an agent runs at: sarsi ceiling all A2.")
def ceiling(target: str = typer.Argument(..., help="Agent id, e.g. sarsi-worker — or 'all'"),
            level: str = typer.Argument(..., help="A0, A1, A2 or A3")) -> None:
    _load()
    agent_id = None if target.lower() == "all" else target
    try:
        changed = admin.set_ceiling(agent_id, level.upper())
    except (KeyError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    console.print(f"ceiling {level.upper()} — {', '.join(changed)}", markup=False,
                  highlight=False)
    # what is written is what is ASKED for; say where it will actually land
    config = _load()
    for row in admin.agent_rows(config):
        if row["id"] in changed and row.get("ceiling_effective") != row["ceiling"]:
            console.print(f"  {row['id']}: runs at {row['ceiling_effective']} until "
                          f"the trust ledger earns {row['ceiling']}", style="yellow")
    console.print("planning still runs at A0; outward acts still stop at you",
                  style="dim")


@app.command("set-token", help="Set one agent's Telegram bot token.")
def set_token(agent_id: str = typer.Argument(..., help="Agent id, e.g. sarsi-worker"),
              token: str = typer.Argument(..., help="Bot token from @BotFather")) -> None:
    _load()
    try:
        admin.set_bot_token(agent_id, token)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    console.print(f"token set for [cyan]{agent_id}[/cyan]")     # never echoed back


# ── §11, the half a single machine has ────────────────────────────────

market_app = typer.Typer(help="Install and inspect market packages on this machine.")
app.add_typer(market_app, name="market")


@market_app.command("install", help="Install an agent package from a directory.")
def market_install(path: str = typer.Argument(..., help="The package directory")) -> None:
    from ai4science.harness.agents.sarsi import market as mk
    config = _load()
    try:
        report = mk.install(config, path)
    except mk.Refused as e:
        # A refusal names what was asked for and why it was not given. "Could
        # not install" would leave the author's request invisible.
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print(f"installed {report.agent_id} {report.version}".rstrip(),
                  markup=False, highlight=False)
    if report.purpose:
        console.print(f"  {report.purpose}", markup=False, highlight=False)
    # Trust is not transitive: every author whose code came with it, and what
    # each part touches. Printed on the way in, because this is the moment the
    # owner is deciding.
    console.print("  code by:", markup=False, highlight=False)
    for a in report.authors:
        touches = ", ".join(a.get("touches") or []) or "nothing declared"
        console.print(f"    {a.get('handle', 'unknown')} — {a.get('part', '?')}"
                      f" — touches {touches}", markup=False, highlight=False)
    console.print(f"  it runs at {reg_everyday()}, with an empty workspace and "
                  f"task list this machine made", markup=False, highlight=False)
    # Which standing it has, said on the way in. An owner installing something
    # nobody has looked at should be told that at the moment they do it, not
    # be left to infer it from the absence of a line.
    console.print(f"  {report.standing}", markup=False, highlight=False)


@market_app.command("list", help="What was installed from the market.")
def market_list() -> None:
    from ai4science.harness.agents.sarsi import market as mk
    rows = mk.installed(_load())
    if not rows:
        console.print("nothing installed from the market — the seven shipped "
                      "with this machine", markup=False, highlight=False)
        return
    for r in rows:
        console.print(f"{r.agent_id} {r.version}".rstrip(), markup=False,
                      highlight=False)
        if r.purpose:
            console.print(f"  {r.purpose}", markup=False, highlight=False)
        who = ", ".join(sorted({a.get("handle", "unknown") for a in r.authors}))
        console.print(f"  code by: {who}", markup=False, highlight=False)


@market_app.command("remove", help="Take an installed package out of the roster.")
def market_remove(agent_id: str = typer.Argument(..., help="Agent id")) -> None:
    from ai4science.harness.agents.sarsi import market as mk
    config = _load()
    try:
        report = mk.remove(config, agent_id)
    except mk.Refused as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print(f"{report.agent_id} removed from the roster", markup=False,
                  highlight=False)
    console.print("  its folder is kept — the history of what it did is not "
                  "an uninstall's to delete", markup=False, highlight=False)


def reg_everyday() -> str:
    from ai4science.harness.agents.sarsi.registry import EVERYDAY_CEILING
    return EVERYDAY_CEILING


@market_app.command("review", help="Ask the acceptance questions of a package.")
def market_review(path: str = typer.Argument(..., help="The package directory")) -> None:
    from ai4science.harness.agents.sarsi import market as mk
    got = mk.review(path)
    for problem in got.problems:
        console.print(f"  - {problem}", markup=False, highlight=False)
    if got.tests:
        console.print("author's claim that it works: "
                      + ", ".join(got.tests), markup=False, highlight=False)
        # Said plainly, because a reader would otherwise assume a green review
        # means the tests passed. Running them to decide whether the author can
        # be trusted is executing untrusted code to find out if it is
        # trustworthy — that is the installer's call, on their machine, after.
        console.print("  (not run — reviewing does not execute the package)",
                      markup=False, highlight=False)
    else:
        console.print("the author claims nothing proves it works",
                      markup=False, highlight=False)
    if not got.ok:
        raise typer.Exit(code=1)
    console.print(f"reviews clean · digest {got.digest[:16]}",
                  markup=False, highlight=False)


@market_app.command("publish", help="Seal a package and put it where a governor can read it.")
def market_publish(path: str = typer.Argument(..., help="The package directory")) -> None:
    from ai4science.harness.agents.sarsi import market as mk
    config = _load()
    try:
        listing = mk.pack(path)
    except mk.Refused as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    # A file-inbox, the same handshake the compute design uses. HTTP later is a
    # change of TRANSPORT: the digest and the signature are what is trusted, and
    # neither cares how the listing travelled.
    box = config.root / "market" / "outbox"
    box.mkdir(parents=True, exist_ok=True)
    body = {"agent_id": listing.agent_id, "version": listing.version,
            "digest": listing.digest, "source": listing.source}
    (box / f"{listing.agent_id}-{listing.digest[:12]}.json").write_text(
        json.dumps(body, indent=2, sort_keys=True))
    console.print(f"published {listing.agent_id} {listing.version}".rstrip(),
                  markup=False, highlight=False)
    console.print(f"  digest {listing.digest}", markup=False, highlight=False)
    console.print(f"  waiting for review in {box}", markup=False,
                  highlight=False)


@app.command("earned", help="What each run owes, and to whom. Records only.")
def earned_cmd() -> None:
    from ai4science.harness.agents.sarsi import earnings as ern
    config = _load()
    total = ern.total(config)
    if not total.runs and not total.unmeasured:
        console.print("nothing recorded yet — a run owes something once it has "
                      "been metered", markup=False, highlight=False)
        return
    console.print(f"treasury {total.treasury:g} · authors {total.author:g} · "
                  f"provider {total.provider:g}  (over {total.runs} run(s))",
                  markup=False, highlight=False)
    for handle, amount in sorted(ern.by_author(config).items()):
        console.print(f"  {handle}: {amount:g}", markup=False, highlight=False)
    if total.unmeasured:
        # The rule the whole module is built on, said where it is read: a total
        # that quietly omitted the unmeasured runs would look complete.
        console.print(f"  {total.unmeasured} run(s) could not be measured, so "
                      f"this is what was seen and not what was spent",
                      markup=False, highlight=False)
    console.print("  this records what is owed and moves nothing — settling is "
                  "the platform's, never this machine's", markup=False,
                  highlight=False)


exchange_app = typer.Typer(help="The node that earns, and never touches your work.")
app.add_typer(exchange_app, name="exchange")


@exchange_app.command("start", help="Start the exchange node, bounded by a budget.")
def exchange_start(budget_pwm: float = typer.Option(
        None, "--budget-pwm", help="How much PWM it may supply before stopping.")) -> None:
    from ai4science.harness.agents.sarsi import exchange as ex
    try:
        got = ex.start(_load(), budget_pwm=budget_pwm)
    except ex.NotAnAgent as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    console.print(got.summary, markup=False, highlight=False)
    console.print("  stop it any time: ai4science sarsi exchange stop",
                  markup=False, highlight=False)


@exchange_app.command("status", help="Is it earning, and how much of its budget is left.")
def exchange_status() -> None:
    from ai4science.harness.agents.sarsi import exchange as ex
    console.print(ex.status(_load()).summary, markup=False, highlight=False)


@exchange_app.command("stop", help="Stop it. Yours to do at any time.")
def exchange_stop() -> None:
    from ai4science.harness.agents.sarsi import exchange as ex
    got = ex.stop(_load())
    console.print(got.summary, markup=False, highlight=False)
    console.print("  what it supplied is kept — stopping it is a decision "
                  "about the future", markup=False, highlight=False)


@app.command("balance", help="The non-exchangeable starting balance: fees only.")
def balance_cmd(do_grant: bool = typer.Option(
        False, "--grant", help="Take this machine's one starting balance.")) -> None:
    from ai4science.harness.agents.sarsi import balance as bal
    config = _load()
    if do_grant:
        try:
            got = bal.grant(config)
        except bal.Refused as e:
            console.print(str(e), style="yellow", markup=False, highlight=False)
            raise typer.Exit(code=1)
        console.print(got.summary, markup=False, highlight=False)
        return
    got = bal.of(config)
    console.print(got.summary, markup=False, highlight=False)
    if got.granted:
        # Said every time it is read, not only on the grant. A figure whose
        # kind is only stated once is a figure somebody will later add to
        # another one.
        console.print("  it can only be spent down, on fees, and there is no "
                      "way to move or sell it", markup=False, highlight=False)
        for row in bal.history(config)[-5:]:
            console.print(f"  {row.pwm:g} — fee for {row.fee_for}",
                          markup=False, highlight=False)


@app.command("problems", help="A field's open problems, in the order they must be solved.")
def problems_cmd(field: str = typer.Argument(
        "", help="e.g. computational-imaging; omit to list the fields")) -> None:
    from ai4science.harness.agents.sarsi import problems as pr
    if not field:
        console.print("fields with a problem list on this machine:",
                      markup=False, highlight=False)
        for name in sorted(pr.FIELDS):
            listing = pr.for_field(name)
            read = sum(1 for p in listing if not p.grounded)
            note = (f"  ({len(listing)} problems, {read} from reading rather "
                    f"than evidence held here)" if read else
                    f"  ({len(listing)} problems, grounded in work done here)")
            console.print(f"  {name}{note}", markup=False, highlight=False)
        return
    listing = pr.for_field(field)
    if not listing:
        # A refusal rather than an empty page: "nobody has written down what
        # this field is trying to solve" is a fact about the field, and silence
        # would read as "there is nothing to solve".
        console.print(f"no problem list for {field!r} on this machine — a field "
                      f"without one has nobody's account of what it is trying "
                      f"to solve, which is not the same as having nothing to "
                      f"solve.\n  known: " + ", ".join(sorted(pr.FIELDS)),
                      markup=False, highlight=False)
        raise typer.Exit(code=1)
    try:
        ordered = pr.order(listing)
    except pr.Unorderable as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    for i, p in enumerate(ordered, 1):
        mark = "done" if p.solved else "open"
        # The id is printed, not only the title: a reader needs a handle to
        # refer to a problem by, and a title is a sentence.
        console.print(f"{i}. [{p.tier}] {p.id} — {p.title}  ({mark})",
                      markup=False, highlight=False)
        # The two lines that make it arguable rather than authoritative: what
        # would settle it, and why it is here and not elsewhere.
        console.print(f"     verified when: {p.verified_when}", markup=False,
                      highlight=False)
        console.print(f"     {p.why}. {p.because}", markup=False,
                      highlight=False)
        if not p.grounded:
            # Said per problem, because a field can be part evidence and part
            # reading — low-dose CT is. A mark on the field alone would let the
            # grounded problems borrow the doubt and the read ones borrow the
            # authority.
            console.print("     (a reading of the field — this machine holds "
                          "no evidence for it)", markup=False, highlight=False)
