"""The board — every task, on whichever door the owner came through.

`/tasks` lists them; `/<task>` opens one; and opening one is also the way into
its `sarsi-claude` session:

| Mode | Who drives | What happens |
|---|---|---|
| **Guided** | the worker | your instruction is steered into the session |
| **Interact** | **you**, in the terminal | steering pauses and you are handed the `tmux` line |
| **History** | nobody | the record is read |

**Interact does not relay.** A relay would leave two things typing into one pane
with a protocol deciding who wins, and would have to decide what a bare digit or
an `esc` means — which the terminal already knows. So the mode is an entry
point: it pauses the worker, marks the plan stale so steering cannot resume by
marching through phases the owner has just abandoned by hand, and stands back.

Everything here is shared by both surfaces, because an agent has one memory and
one set of sessions regardless of which door was used.
"""
from __future__ import annotations

from typing import Any, List, Optional

from ai4science.harness.agents.sarsi import plan as pl, session as ses, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

COMMANDS = ("/tasks", "/<task>", "/guided <task> <instruction>",
            "/interact <task>", "/resume <task>", "/history <task>",
            "/plan <task>", "/edit <task> <phase#> <new Verified when line>")


def handle(config: Config, agent: Agent, text: str, *, surface: str,
           runtime: Optional[Any] = None) -> str:
    body = (text or "").strip()
    if not body.startswith("/"):
        return _not_a_command(config, agent, body, surface)

    verb, _, rest = body[1:].partition(" ")
    verb, rest = verb.strip(), rest.strip()

    if verb == "tasks":
        return _tasks(config, agent)
    if verb in ("guided", "interact", "resume", "history", "plan", "edit"):
        token, _, tail = rest.partition(" ")
        found = _resolve(config, agent, token.strip())
        if isinstance(found, str):
            return found
        return {"guided": _guided, "interact": _interact, "resume": _resume,
                "history": _history, "plan": _plan, "edit": _edit}[verb](
                    config, agent, found, tail.strip(), runtime)

    found = _resolve(config, agent, verb)      # `/<task>` opens one
    if isinstance(found, str):
        # a token that is not a task id at all is a mistyped command, and the
        # useful answer names the commands rather than the missing task
        return found if verb.startswith("tsk") else _unknown(agent)
    return _open(config, agent, found)


# ── listing ───────────────────────────────────────────────────────────

def _tasks(config: Config, agent: Agent) -> str:
    rows = tsk.all_of(config, agent)
    if not rows:
        return f"{agent.id}: no tasks."
    lines = [f"{agent.id} — {len(rows)} task(s):"]
    for t in rows:
        # never idle-looking when it is actually blocked: say which
        waiting = ", ".join(t.awaiting) or t.blocked_by or ""
        suffix = f" — waiting on {waiting}" if waiting else ""
        lines.append(f"  /{t.id}  {t.goal}  [{t.state}]{suffix}")
    return "\n".join(lines)


def _open(config: Config, agent: Agent, t: tsk.Task) -> str:
    lines = [f"{t.id} — {t.goal}", f"state: {t.state}"]
    if t.awaiting:
        lines.append(f"waiting on you to grant: {', '.join(t.awaiting)}")
    if t.plan_version:
        flags = []
        if t.plan_stale:
            flags.append("stale — its criteria are withheld")
        if t.plan_owner_edited:
            flags.append("edited by you — polish may only propose")
        lines.append(f"plan: {t.plan_version}.md" +
                     (f" ({'; '.join(flags)})" if flags else ""))
        for i, criterion in enumerate(t.criteria, start=1):
            lines.append(f"  {i}. Verified when: {criterion}")
    session = (t.session or {}).get("name")
    lines.append(f"session: {session or 'not started'}")
    if t.verdict:
        lines.append(f"verdict: {t.verdict.get('state')} — {t.verdict.get('why', '')}")
    lines += ["",
              f"Guided   /guided {t.id} <instruction>   — the worker steers it",
              f"Interact /interact {t.id}               — you take the wheel in tmux",
              f"History  /history {t.id}                — what has happened",
              f"Edit     /edit {t.id} 1 <new criterion> — your edit wins"]
    return "\n".join(lines)


# ── the three modes ───────────────────────────────────────────────────

def _guided(config, agent, t, instruction, runtime):
    if not instruction:
        return f"say what to steer: /guided {t.id} <instruction>"
    if not t.session:
        return f"{t.id} has no session yet — nothing to steer."
    if t.steering_paused:
        # the owner has the wheel; the worker must not type over them
        return (f"you have the wheel on {t.id} — the worker is standing by.\n"
                f"hand it back with /resume {t.id} when you are done.")
    (runtime or ses.MachineRuntime()).send(t.session["name"], instruction)
    return f"steered {t.id}: {instruction}"


def _interact(config, agent, t, _tail, runtime):
    if not t.session:
        return f"{t.id} has no session yet — nothing to attach to."
    name = t.session["name"]
    t.steering_paused = True
    t.plan_stale = True                 # you may be abandoning phases by hand
    t.criteria = []                     # a stale plan's criteria are withheld
    tsk._touch(agent, t, __import__("time").time)
    return (f"you have the wheel on {t.id}. The worker is standing by and its "
            f"plan is marked stale, so it will not drive back through phases "
            f"you change by hand.\n"
            f"  tmux attach -t {name}\n"
            f"  Ctrl-b d to step out, then /resume {t.id} to hand it back.")


def _resume(config, agent, t, _tail, runtime):
    t.steering_paused = False
    tsk._touch(agent, t, __import__("time").time)
    return (f"the worker has {t.id} again. Its plan is still marked stale until "
            f"you edit it or it is redrafted.")


def _history(config, agent, t, _tail, runtime):
    from ai4science.harness.agents.sarsi import ledger
    rows = [r for r in ledger.read(config, "reports") if r.get("task") == t.id]
    if not rows:
        return f"{t.id}: nothing recorded yet."
    lines = [f"{t.id} — {len(rows)} record(s):"]
    for r in rows[-10:]:
        lines.append(f"  {r.get('at', '')}  {r.get('state', '')}  "
                     f"{'; '.join(r.get('evidence') or [])[:120]}")
    session = (t.session or {}).get("name")
    if session:
        lines.append(f"the session's own transcript: tmux attach -t {session}")
    return "\n".join(lines)


def _plan(config, agent, t, _tail, runtime):
    plan = tsk.read_plan(config, agent, t)
    return plan.render() if plan else f"{t.id} has no plan yet."


def _edit(config, agent, t, tail, runtime):
    number, _, criterion = tail.partition(" ")
    criterion = criterion.strip()
    if not number.isdigit() or not criterion:
        return f"say which phase and what it should be: /edit {t.id} 1 <criterion>"
    plan = tsk.read_plan(config, agent, t)
    if plan is None:
        return f"{t.id} has no plan to edit."
    index = int(number) - 1
    if index < 0 or index >= len(plan.phases):
        return (f"{t.id} has {len(plan.phases)} phase(s); there is no phase "
                f"{number}.")
    phases: List[pl.Phase] = list(plan.phases)
    phases[index] = pl.Phase(title=phases[index].title, body=phases[index].body,
                             verified_when=criterion)
    edited = plan.owner_edit(phases=phases)
    path = tsk.dir_of(agent, t.id) / f"{t.plan_version}.md"
    path.write_text(edited.render())
    t.criteria = edited.criteria()
    t.plan_stale = False               # an edit is the mission restated
    t.plan_owner_edited = True
    tsk._touch(agent, t, __import__("time").time)
    return (f"{t.id} phase {number} now reads: {criterion}\n"
            f"that is the standard the verifier will apply.")


# ── fallbacks ─────────────────────────────────────────────────────────

def _resolve(config: Config, agent: Agent, token: str):
    """A task id, or a unique prefix of one. Never a guess."""
    token = (token or "").strip()
    rows = tsk.all_of(config, agent)
    exact = [t for t in rows if t.id == token]
    if exact:
        return exact[0]
    hits = [t for t in rows if t.id.startswith(token)] if token else []
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # guessing which one the owner meant is how the wrong session is stopped
        return ("which one? " + ", ".join(f"/{t.id} ({t.goal})" for t in hits))
    return f"no task {token!r} for {agent.id} — /tasks lists them."


def _not_a_command(config: Config, agent: Agent, body: str, surface: str) -> str:
    role = ("manager — I route and answer; I do not drive sessions"
            if not agent.is_worker else
            "worker — I hold tasks and drive sarsi-claude")
    return (f"[{agent.id}] {role}.\n"
            f"heard on {surface}: {body}\n"
            f"I cannot plan this yet — /tasks shows what I am holding.")


def _unknown(agent: Agent) -> str:
    return (f"[{agent.id}] I do not know that one. I understand:\n  " +
            "\n  ".join(COMMANDS))
