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

import time
from typing import Any, List, Optional

from ai4science.harness.agents.sarsi import memory, plan as pl, session as ses, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

COMMANDS = ("/tasks", "/<task>", "/guided <task> <instruction>",
            "/interact <task>", "/resume <task>", "/history <task>",
            "/plan <task>", "/edit <task> <phase#> <new Verified when line>")


def handle(config: Config, agent: Agent, text: str, *, surface: str,
           runtime: Optional[Any] = None, pane: Optional[Any] = None) -> str:
    body = (text or "").strip()
    if not body.startswith("/"):
        verb = _self_verb(body)
        if verb:
            return verb(config, agent)
        # Inside a task, plain words are about THAT task — that is what being
        # "in" one means. With no cursor they are not steered anywhere: a
        # message with nowhere to go must not pick a session for itself.
        standing = _standing(config, agent, surface)
        if body.lower().rstrip("?").strip() == "why":
            # Asked from inside a task, it is about that task — naming it again
            # is the friction the cursor exists to remove.
            if standing is None:
                return (f"which task? /why <task> — or open one with /<task> "
                        f"first. /tasks lists them.")
            return _why(config, agent, standing, "", runtime)
        if standing is not None:
            return _guided(config, agent, standing, body, runtime)
        return _classified(config, agent, body, surface)

    verb, _, rest = body[1:].partition(" ")
    verb, rest = verb.strip(), rest.strip()

    if verb == "new":
        return _new(config, agent, rest, surface)
    if verb in ("tasks", "task"):
        # stepping back out to the board is explicit, so the cursor never
        # silently follows something the owner did not choose
        _stand(config, agent, None, surface)
        return _tasks(config, agent)
    if verb == "archived":
        return _archived(config, agent)
    if verb == "who":
        return _who(config, rest)
    if verb == "questions":
        return _questions(config, agent)
    if verb == "answer":
        token, _, tail = rest.partition(" ")
        found = _resolve(config, agent, token.strip())
        if isinstance(found, str):
            return found
        return _answer(config, agent, found, tail.strip(), runtime, pane)
    if verb in ("guided", "interact", "resume", "history", "plan", "edit",
                "stop", "archive", "reopen", "resume-task", "goal", "why"):
        token, _, tail = rest.partition(" ")
        found = _resolve(config, agent, token.strip())
        if isinstance(found, str):
            return found
        return {"guided": _guided, "interact": _interact, "resume": _resume,
                "history": _history, "plan": _plan, "edit": _edit,
                "stop": _stop, "archive": _archive, "reopen": _reopen,
                "resume-task": _resume_task, "goal": _goal,
                "why": _why}[verb](
                    config, agent, found, tail.strip(), runtime)

    found = _resolve(config, agent, verb)      # `/<task>` opens one
    if isinstance(found, str):
        # a token that is not a task id at all is a mistyped command, and the
        # useful answer names the commands rather than the missing task
        return found if verb.startswith("tsk") else _unknown(agent)
    _stand(config, agent, found.id, surface)   # opening one is standing in it
    return _open(config, agent, found)


# ── where this surface is standing ────────────────────────────────────

def _stand(config: Config, agent: Agent, task_id, surface: str) -> None:
    from ai4science.harness.agents.sarsi import entry
    try:
        entry.stand_in(config, agent, task_id, surface=surface)
    except Exception:
        pass          # a cursor that cannot be written must not eat the command


def _standing(config: Config, agent: Agent, surface: str):
    from ai4science.harness.agents.sarsi import entry
    try:
        here = entry.current(config, agent, surface=surface)
    except Exception:
        return None
    return tsk.get(config, agent, here) if here else None


def _new(config: Config, agent: Agent, goal: str, surface: str) -> str:
    """Open a task from inside the worker, and stand in it.

    The empty state needs a way *out* of it: until this existed, nothing created
    a task from inside a worker and the only door was the CLI.
    """
    goal = (goal or "").strip()
    if not goal:
        return f"usage: /new <goal, one sentence>"
    if not agent.is_worker:
        return f"{agent.id} is a manager: it holds no tasks."

    # `/new the goal is please write X` files as `write X` — the framing
    # describes the sentence, not the work, and it would read back as noise
    # in every listing thereafter. Only a clean directive is rewritten;
    # anything else files as typed, because /new IS the explicit act and
    # second-guessing it here would refuse goals the owner chose.
    from ai4science.harness.agents.sarsi import intent as _intent
    got = _intent.classify(goal)
    if got.kind == "directive":
        goal = got.goal

    from ai4science.harness.agents.sarsi import worker as wk
    try:
        directive = wk.Directive(agent_id=agent.id, goal=goal)
        out = wk.admit(config, agent, directive)
    except (wk.BadDirective, wk.NotAWorker) as e:
        return str(e)
    if not out.admitted:
        return f"{out.message}\nnot queued — nothing is waiting on this"

    t = tsk.attach_plan(config, agent, tsk.create(config, agent, directive),
                        pl.draft(directive))
    t = tsk.start(config, agent, t)
    _stand(config, agent, t.id, surface)
    lines = [f"{agent.id} holds {t.id} — {t.state}",
             "  plan drafted; sarsi-claude agrees it before work starts",
             "  you are now in it — plain words go to its session",
             f"  run it: ai4science sarsi run {agent.id} {t.id}"]
    if t.awaiting:
        lines.insert(1, f"  waiting on: {', '.join(t.awaiting)}")
    if t.blocked_by:
        lines.append(f"  not started — {t.blocked_by}")
    return "\n".join(lines)


# ── listing ───────────────────────────────────────────────────────────

def _tasks(config: Config, agent: Agent) -> str:
    rows = tsk.all_of(config, agent)
    # counted, not listed: the record has to stay visible or archiving reads as
    # deleting, but a growing archive must not bury the live work
    closed = len(tsk.all_of(config, agent, archived=True))
    tail = f"\n{closed} archived — /archived to list them" if closed else ""
    if not rows:
        return f"{agent.id}: no tasks.{tail}"
    lines = [f"{agent.id} — {len(rows)} task(s):"]
    for t in rows:
        # never idle-looking when it is actually blocked: say which
        waiting = ", ".join(t.awaiting) or t.blocked_by or ""
        suffix = f" — waiting on {waiting}" if waiting else ""
        label = f"{t.name}---task  " if t.name else ""
        lines.append(f"  /{t.id}  {label}{t.goal}  [{t.state}]{suffix}")
    return "\n".join(lines) + tail


def _archived(config: Config, agent: Agent) -> str:
    rows = tsk.all_of(config, agent, archived=True)
    if not rows:
        return f"{agent.id}: nothing archived."
    lines = [f"{agent.id} — {len(rows)} archived:"]
    for t in rows:
        verdict = (t.verdict or {}).get("state") or "no verdict"
        lines.append(f"  /{t.id}  {t.goal}  [{verdict}]")
    lines.append("re-open one with /reopen <task>")
    return "\n".join(lines)


def _who(config: Config, demand: str) -> str:
    """"Who should do this?" — the fleet question, answerable from any door."""
    from ai4science.harness.agents.sarsi import triage
    try:
        return triage.suggest(config, demand).summary
    except ValueError as e:
        return str(e)


def _questions(config: Config, agent: Agent) -> str:
    from ai4science.harness.agents.sarsi import questions as qst
    rows = qst.open_of(config, agent)
    if not rows:
        return f"{agent.id}: no open questions."
    lines = [f"{agent.id} — {len(rows)} open question(s):"]
    for q in rows:
        lines.append(f"  /{q.task_id}  {q.text}")
        if q.why:
            lines.append(f"      ({q.why})")
    lines.append('answer one with: /answer <task> <question> | <your answer>')
    return "\n".join(lines)


def _answer(config: Config, agent: Agent, t: tsk.Task, tail: str, runtime,
            pane=None) -> str:
    """`/answer <task> <question> | <answer>`.

    The separator is explicit because a question and an answer are both free
    text; guessing where one ends would sometimes deliver half of each.
    """
    from ai4science.harness.agents.sarsi import questions as qst
    if "|" not in tail:
        return (f"usage: /answer {t.id} <the question> | <your answer>\n"
                f"/questions lists what is open")
    question, _, reply = tail.partition("|")
    try:
        qst.answer(config, agent, t, question.strip(), reply.strip(),
                   runtime=runtime, pane=pane)
    except (qst.NotAsked, qst.NoSession, qst.NotDelivered) as e:
        return str(e)
    return f"answered — {t.id} has been told, and the question is closed"


# ── closing one ───────────────────────────────────────────────────────

def _stop(config: Config, agent: Agent, t: tsk.Task, rest: str,
          runtime) -> str:
    """Stop it and take its session with it. Resumable — the plan survives."""
    from ai4science.harness.agents.sarsi import session as ses
    t = ses.stop(config, agent, t, runtime=runtime)
    return (f"{t.id} stopped — its session is closed and its slot is free.\n"
            f"pick it up again with /resume-task {t.id}")


def _archive(config: Config, agent: Agent, t: tsk.Task, rest: str,
             runtime) -> str:
    from ai4science.harness.agents.sarsi import session as ses
    t = ses.stop(config, agent, t, runtime=runtime, archive=True)
    return (f"{t.id} archived — off the board, and kept.\n"
            f"its plan, verdict and history stay readable with /{t.id}")


def _resume_task(config: Config, agent: Agent, t: tsk.Task, rest: str,
                 runtime) -> str:
    """Put a stopped task back to work.

    Named apart from `/resume`, which hands the *steering* back to the worker
    after Interact. Two different resumes on one board is exactly the kind of
    collision that stops the wrong thing.
    """
    try:
        t = tsk.resume(config, agent, t)
    except tsk.Archived as e:
        return str(e)
    if t.blocked_by == "concurrency":
        return (f"{t.id} is ready but every slot is busy — stop or archive one "
                f"first (/tasks shows which).")
    return (f"{t.id} is {t.state} again.\n"
            f"it has no session yet: ai4science sarsi run {agent.id} {t.id}")


def _reopen(config: Config, agent: Agent, t: tsk.Task, rest: str,
            runtime) -> str:
    if t.state != tsk.ARCHIVED:
        return f"{t.id} is not archived — it is {t.state}."
    t = tsk.reopen(config, agent, t)
    return (f"{t.id} is back on the board, stopped.\n"
            f"start it when you want it: /resume-task {t.id}")


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
    if not ses.drivable(agent.spec):
        # In words, not an exception: this answer goes back to a person on
        # Telegram. They are the delivery mechanism, so hand them the text.
        return (f"{agent.id} runs the {agent.spec!r} interface, which this loop "
                f"cannot read — typing at it is keystrokes at an unknown "
                f"screen. Deliver it yourself:\n"
                f"  tmux attach -t {t.session['name']}\n"
                f"  {instruction}")
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


def _why(config, agent, t, tail, runtime):
    """The goal, the criteria, and the last verdict — in one answer."""
    from ai4science.harness.agents.sarsi import why as wy
    return wy.explain(config, agent, t)


def _goal(config, agent, t, tail, runtime):
    """Move the goal, and take the plan with it.

    A plan drafted for the old goal, still attached to the new one, is a plan
    that verifies the wrong thing — the most expensive kind of wrong, because
    it looks settled. So the plan is re-drafted, the agreement is dropped (it
    was agreed about a different goal), and a working session is told rather
    than left finishing the old task perfectly.

    The owner's own criteria are kept across the move: they are the owner's
    words about what done means, and a re-draft may propose around them but
    never over them.
    """
    goal = (tail or "").strip()
    if not goal:
        return (f"usage: /goal {t.id} <the new goal, one sentence>\n"
                f"it currently reads: {t.goal}")

    from ai4science.harness.agents.sarsi import worker as wk
    record = dict(t.directive or {})
    try:
        directive = wk.Directive(
            agent_id=agent.id, goal=goal,
            scope=list(record.get("scope") or []),
            requires_tools=list(record.get("requires_tools") or []),
            requires_secrets=list(record.get("requires_secrets") or []))
    except wk.BadDirective as e:
        return str(e)

    owner_criteria = list(t.criteria) if t.plan_owner_edited else []
    was = t.goal
    t.goal = goal
    t.directive = directive.as_record()
    t = tsk.attach_plan(config, agent, t, pl.draft(directive))
    # The plan was re-drafted for a different goal; none of the old per-phase
    # answers are about it.
    tsk.clear_phase(t, None)
    memory.record(config, agent, "rollback",
                  f"{t.id} rolled back: goal changed from {was[:120]!r}",
                  f"the plan was re-drafted for the new goal: {goal[:200]}",
                  now=time.time)
    if owner_criteria:
        t.criteria = owner_criteria           # the owner's words survive
        t.plan_owner_edited = True
    t.plan_agreed = False                     # agreed about a different goal
    t.plan_stale = False                      # restated, not abandoned
    t = tsk._touch(agent, t, time.time)

    lines = [f"{t.id} goal is now: {goal}",
             f"  was: {was}",
             f"  the plan was re-drafted for it and is no longer agreed — "
             f"{agent.id} and sarsi-claude settle it again"]
    if owner_criteria:
        lines.append(f"  your criteria were kept: {'; '.join(owner_criteria)}")
    if (t.session or {}).get("name"):
        from ai4science.harness.agents.sarsi import session as ses
        notice = (f"The owner has changed this task's goal. It is now: {goal}\n"
                  f"Stop working the old goal and re-read the plan file.")
        try:
            ses.guide(config, agent, t, notice, runtime=runtime, by_owner=True)
            lines.append("  its running session has been told")
        except ses.NotDrivable:
            # The goal change is the record edit; telling the session is a
            # courtesy on top of it. Letting this escape would mean an attended
            # agent's goal cannot be changed at all while it holds a session —
            # and saying "has been told" would be worse.
            lines.append(f"  its session runs the {agent.spec!r} interface, so "
                         f"it has NOT been told — deliver this yourself:")
            lines.append(f"    tmux attach -t "
                         f"{(t.session or {}).get('name', '?')}")
            lines.append(f"    {notice}")
    return "\n".join(lines)


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
    # That phase was judged against a standard that no longer exists. Keeping
    # the PASS would carry a verdict about a question nobody asks any more.
    tsk.clear_phase(t, index)
    memory.record(config, agent, "rollback",
                  f"{t.id} rolled back: phase {number} criterion replaced",
                  f"the phase was judged against a standard that no longer exists; "
                  f"it now reads: {criterion[:200]}", now=time.time)
    t.plan_stale = False               # an edit is the mission restated
    t.plan_owner_edited = True
    t.plan_agreed = True               # you have settled it; no more drafting
    tsk._touch(agent, t, __import__("time").time)
    return (f"{t.id} phase {number} now reads: {criterion}\n"
            f"that is the standard the verifier will apply.")


# ── the self-model, and the loop that changes the playbook ────────────

def _self_verb(body: str):
    """The four deterministic verbs, matched exactly rather than guessed at."""
    low = body.strip().lower().rstrip("?.!")
    if low in ("self model", "self-model", "how competent are you",
               "what can you do"):
        return _self_model
    if low in ("improve yourself", "improve", "rsi"):
        return _improve
    if low in ("yes", "y", "sign", "approve"):
        return _sign
    if low in ("no", "n", "discard", "decline"):
        return _decline
    return None


def _self_model(config: Config, agent: Agent) -> str:
    from ai4science.harness.agents.sarsi import selfmodel as sm
    return sm.render(config, agent)


def _improve(config: Config, agent: Agent) -> str:
    from ai4science.harness.agents.sarsi import playbook as pb, selfmodel as sm
    evidence = sm.evidence_for_rsi(config, agent)
    candidate = pb.propose(config, agent, evidence=evidence)
    if candidate.change is None:
        # the honest outcome when nothing measured justifies one
        return f"[{agent.id}] {candidate.rationale}"
    return (f"[{agent.id}] I propose: {candidate.change}\n"
            f"why: {candidate.rationale}\n"
            f"held — reply `yes` to sign it, `no` to discard. I cannot promote "
            f"this myself.")


def _sign(config: Config, agent: Agent) -> str:
    from ai4science.harness.agents.sarsi import playbook as pb
    out = pb.sign(config, agent, by_owner=True)
    if not out.adopted:
        return f"[{agent.id}] nothing was pending — nothing changed."
    return (f"[{agent.id}] promoted — playbook now v{out.version}. "
            f"The parameters are live on the next action.\n{out.note}")


def _decline(config: Config, agent: Agent) -> str:
    from ai4science.harness.agents.sarsi import playbook as pb
    pb.discard(config, agent)
    return f"[{agent.id}] discarded — the playbook is unchanged."


# ── fallbacks ─────────────────────────────────────────────────────────

def _resolve(config: Config, agent: Agent, token: str):
    """A task id, or a unique prefix of one. Never a guess."""
    token = (token or "").strip()
    # archived tasks are off the BOARD, not out of reach: `/reopen` and reading
    # the record of finished work both have to find them by id
    rows = tsk.all_of(config, agent) + tsk.all_of(config, agent, archived=True)
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


def _classified(config: Config, agent: Agent, body: str, surface: str) -> str:
    """A plain line with no cursor, told apart before it is answered.

    Every kind used to get the same reply — 'heard on cli: hi / I cannot plan
    this yet' — which reads as a failed directive whatever the owner said. The
    console door already classifies; a door that does not is the second
    classifier problem in reverse: one decides, the other shrugs.

    This door never files a task from plain chat — creation stays explicit —
    so a directive is answered with the exact /new to type, framing already
    stripped."""
    if not agent.is_worker:
        # A manager holds no tasks, so /new is not an offer it can make —
        # classifying the line would only sharpen a suggestion that is wrong
        # on this agent. It says what it is and where goals go instead.
        return (f"[{agent.id}] manager — I route and answer; I do not drive "
                f"sessions.\nheard on {surface}: {body}\n"
                f"a worker takes goals — `sarsi agents` lists them.")
    from ai4science.harness.agents.sarsi import intent as _intent
    got = _intent.classify(body)

    if got.kind == "greeting":
        return (f"[{agent.id}] hello — /tasks shows what I am holding, "
                f"/new <goal> opens a task.")

    if got.kind == "question":
        from ai4science.harness.agents.sarsi import selfaware as _sa
        if _sa.is_about_self(body):
            return _self_model(config, agent)
        return (f"[{agent.id}] that is a question I cannot answer on this "
                f"door.\nheard on {surface}: {body}\n"
                f"to make it a task instead: /new {body}")

    if got.kind in ("meta", "ambiguous"):
        return f"[{agent.id}] {got.why}"

    # A directive is a goal — and still not a task, until the owner says so.
    return (f"[{agent.id}] that reads as a goal:\n"
            f"  {got.goal}\n"
            f"file it: /new {got.goal}")


def _unknown(agent: Agent) -> str:
    return (f"[{agent.id}] I do not know that one. I understand:\n  " +
            "\n  ".join(COMMANDS))
