"""`ai4science sarsi …` — the CLI door onto the sarsi agents.

Thin by design: every decision lives in `harness.agents.sarsi`, so the CLI and
the Telegram surface reach the same agent through the same code. A surface is a
door, not a scope.
"""
from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from ai4science.harness.agents.sarsi import admin, registry as reg

app = typer.Typer(help="sarsi worker agents on this machine.", no_args_is_help=True)
console = Console()


def _load() -> reg.Config:
    try:
        return reg.load()
    except reg.ConfigError as e:
        console.print(f"[red]registry error:[/red] {e}")
        raise typer.Exit(code=2)


@app.command("init", help="Write the seven-agent registry and create each agent's directories.")
def init(owner_id: str = typer.Option(..., "--owner-id",
                                      help="Your Telegram user id — the only id whose messages are honored.")) -> None:
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
    config = _load()
    table = Table(title="sarsi agents", show_lines=False)
    table.add_column("Agent", style="cyan")
    table.add_column("Role")
    table.add_column("Drives sessions")
    table.add_column("Ceiling")
    table.add_column("Telegram")
    rows = admin.agent_rows(config)
    for row in rows:
        # the invariant, shown rather than assumed: the manager may not execute
        drives = "[green]yes[/green]" if row["drives_sessions"] else "[yellow]no[/yellow]"
        table.add_row(row["id"], row["role"], drives, row["ceiling"], row["telegram"])
    console.print(table)
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
def ask(agent_id: str = typer.Argument(..., help="Agent id, e.g. work"),
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
    reply = gateway.handle(config, agent=agent, text=text, surface=router.CLI_CHANNEL)
    # markup off: an agent's reply is data. `[abraham]` is a name, not a style.
    console.print(reply or "(no reply)", markup=False, highlight=False)


@app.command("do", help="Hand one worker a directive: a goal, and what it will need.")
def do(agent_id: str = typer.Argument(..., help="Worker id, e.g. work"),
       goal: str = typer.Argument(..., help="The goal — one sentence, not the conversation"),
       tool: List[str] = typer.Option(None, "--tool",
                                      help="A tool the work needs (repeatable)."),
       secret: List[str] = typer.Option(None, "--secret",
                                        help="A secret the work will need (repeatable).")) -> None:
    from ai4science.harness.agents.sarsi import worker

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

    t = tsk.attach_plan(config, agent, tsk.create(config, agent, directive),
                        pl.draft(directive))
    t = tsk.start(config, agent, t)
    console.print(f"{agent_id} holds {t.id} — {t.state}", markup=False, highlight=False)
    if t.awaiting:
        # asking here is the point of the plan step, and it names what it wants
        console.print("waiting on you to grant:", style="yellow")
        for permission in t.awaiting:
            console.print(f"  {permission}", markup=False, highlight=False)
        console.print(f"grant it with: ai4science sarsi grant {agent_id} {t.id} "
                      f"\"{t.awaiting[0]}\"", style="dim", markup=False, highlight=False)
    elif t.blocked_by:
        console.print(f"not started — {t.blocked_by}", style="yellow")


@app.command("tasks", help="Every task this worker holds, and what each is waiting for.")
def tasks(agent_id: str = typer.Argument(..., help="Worker id, e.g. work")) -> None:
    from ai4science.harness.agents.sarsi import task as tsk

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    rows = tsk.all_of(config, agent)
    if not rows:
        console.print(f"{agent_id}: no tasks")
        return
    table = Table(title=f"{agent_id} — tasks", show_lines=False)
    table.add_column("Task", style="cyan")
    table.add_column("Goal")
    table.add_column("State")
    table.add_column("Waiting on")
    for t in rows:
        # a task never looks idle when it is actually blocked: say which
        waiting = ", ".join(t.awaiting) or (t.blocked_by or "—")
        table.add_row(t.id, t.goal, t.state, waiting)
    console.print(table)


@app.command("plan", help="Show one task's plan — its phases, criteria, and declared permissions.")
def plan_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
             task_id: str = typer.Argument(..., help="Task id, e.g. tsk_…")) -> None:
    from ai4science.harness.agents.sarsi import task as tsk

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = tsk.get(config, agent, task_id)
    if t is None:
        console.print(f"[red]no task {task_id!r} for {agent_id}[/red]")
        raise typer.Exit(code=2)
    plan = tsk.read_plan(config, agent, t)
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


@app.command("run", help="Hand a task's plan to sarsi-claude — starts its governed session.")
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
    except ses.NotReady as e:
        console.print(str(e), style="yellow", markup=False, highlight=False)
        raise typer.Exit(code=1)
    except ses.CouldNotStart as e:
        console.print(str(e), style="red", markup=False, highlight=False)
        raise typer.Exit(code=1)
    name = (t.session or {}).get("name", "?")
    console.print(f"{t.id} — {t.state} in session {name}",
                  markup=False, highlight=False)
    console.print(f"take the wheel yourself: tmux attach -t {name}   "
                  f"(Ctrl-b d hands it back)", style="dim",
                  markup=False, highlight=False)


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


@app.command("check", help="Ask the independent verifier whether this task's goal is met.")
def check_cmd(agent_id: str = typer.Argument(..., help="Worker id"),
              task_id: str = typer.Argument(..., help="Task id"),
              evidence: str = typer.Option("", "--evidence",
                                           help="The visible evidence to judge."),
              no_model: bool = typer.Option(False, "--no-model",
                                            help="Do not call a model; report that no verifier was available."),
              engine: str = typer.Option("", "--engine",
                                         help="Which engine judged (recorded with the verdict).")) -> None:
    from ai4science.harness.agents.sarsi import session as ses, verifier as vf

    config = _load()
    agent = _worker_or_exit(config, agent_id)
    t = _task_or_exit(config, agent, task_id)
    judge = vf.unavailable("--no-model was given") if no_model else vf.default_verifier()
    t = ses.verify(config, agent, t, verifier=judge, evidence=evidence,
                   engine=engine or None)
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


@app.command("set-token", help="Set one agent's Telegram bot token.")
def set_token(agent_id: str = typer.Argument(..., help="Agent id, e.g. work"),
              token: str = typer.Argument(..., help="Bot token from @BotFather")) -> None:
    _load()
    try:
        admin.set_bot_token(agent_id, token)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2)
    console.print(f"token set for [cyan]{agent_id}[/cyan]")     # never echoed back
