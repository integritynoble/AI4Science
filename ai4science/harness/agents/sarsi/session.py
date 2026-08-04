"""`ASG` — the worker hands the plan to `sarsi-claude`, and takes the verdict back.

**This is the seam.** Below it the 27-node session loop runs unchanged; this
module owns only what sits above it:

  * **only a worker may assign.** The manager may tell a worker to work.
  * **the session is handed the PLAN, not the wish.** The kickoff names the plan
    file and the earliest incomplete phase, because the plan's `Verified when:`
    lines *are* the verifier's criteria — a session driven from the goal alone is
    judged against a standard the owner never reviewed.
  * **the kickoff does not carry the conversation.** What crosses is what the
    session needs; that is what keeps its context bounded independently of the
    chat's.
  * **one task, one session.** Stopping one task cannot disturb another.
  * **the verdict comes from a verifier.** There is no path from the worker to a
    PASS, and a verdict judged by the same engine that did the work says so
    rather than claiming an independence it does not have.

The runtime (tmux + Claude Code) and the verifier are injected, so every rule
above is testable without a terminal or a model.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from ai4science.harness.agents.sarsi import ledger, plan as pl, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config
from ai4science.harness.agents.sarsi.worker import NotAWorker

PASS = "PASS"
FAIL = "FAIL"
PLAN_FILE = "plan0.md"
#: A copy of the worker's seed, so "did the session engage?" is answerable.
SEED_FILE = ".plan-seed.md"


class NotReady(Exception):
    """The task is not ready to be assigned — and this says what it is waiting for."""


class CouldNotStart(Exception):
    """The session would not start. Reported, never pretended around."""


class SpecUnavailable(Exception):
    """The ai4science agent this sarsi agent is built on is not installed."""


class OwnerHasTheWheel(Exception):
    """The owner is driving. The worker stands down — top of the ladder."""


class MachineRuntime:
    """The real one: the machine agent's tmux session control."""

    #: what actually executes the session, for the independence comparison
    engine = "claude"

    def start(self, name: str, cwd: str, *, govern: bool, ceiling: str,
              env: Optional[Dict[str, str]] = None,
              spec: str = "claude-code") -> Dict[str, Any]:
        from ai4science.harness.agents.machine import sessions
        if env:
            # The secret reaches the local session and nothing that outlives it.
            import os
            os.environ.update({_env_key(k): v for k, v in env.items()})
        # `claude-code` is Claude Code itself; anything else runs through the
        # ai4science harness in that mode.
        binary = "claude" if spec == "claude-code" else None
        if binary:
            return sessions.start_session(name, cwd, govern=govern, ceiling=ceiling)
        return sessions.start_session(name, cwd, govern=govern, ceiling=ceiling,
                                      claude_bin=f"ai4science chat --mode {spec}")

    def send(self, name: str, text: str) -> Dict[str, Any]:
        from ai4science.harness.agents.machine import sessions
        return sessions.send_to_session(name, text)

    def stop(self, name: str) -> Dict[str, Any]:
        from ai4science.harness.agents.machine import sessions
        return sessions.kill_session(name)

    def set_ceiling(self, name: str, ceiling: str) -> Dict[str, Any]:
        """Change a live session's ceiling.

        The governance hook reads the supervisor record on every tool call, so
        this takes effect without restarting the session.
        """
        from ai4science.harness.agents.machine import supervisor
        return supervisor.update(name, ceiling=ceiling) or {}


#: Specs whose interface the supervision loop can actually read. Its gate
#: detection, stranded-prompt reading and busy marker are tuned to Claude
#: Code's TUI; another interface may be STARTED, and is reported as not
#: drivable rather than quietly mis-driven.
DRIVABLE_SPECS = {"claude-code", "codex"}


def drivable(spec: str) -> bool:
    return spec in DRIVABLE_SPECS


def installed_specs() -> set:
    try:
        from ai4science.harness.agents import registry as ar
        return set(ar.AGENT_REGISTRY)
    except Exception:
        return set()


def assign(config: Config, agent: Agent, task: tsk.Task, *,
           runtime: Optional[Any] = None, vault_prompt: Optional[Callable] = None,
           installed: Optional[Callable[[], set]] = None,
           now=time.time) -> tsk.Task:
    if not agent.is_worker:
        raise NotAWorker(
            f"{agent.id} is a manager: assigning a task to sarsi-claude may be "
            f"performed only by a worker")
    if task.awaiting:
        raise NotReady("this task is still waiting on a grant: "
                       + ", ".join(task.awaiting))

    if task.session:
        return task                          # one task, one session

    # The spec this agent is built on has to be here. Substituting a generalist
    # would run the wrong agent under the right label, which is worse than not
    # starting at all.
    available = (installed or installed_specs)()
    if available and agent.spec not in available:
        raise SpecUnavailable(
            f"{agent.id} is built on the {agent.spec!r} agent, which is not "
            f"installed here. Installed: {', '.join(sorted(available))}")

    # VLT for the secrets the DIRECTIVE declared. It has to be here rather than
    # at release: a secret reaches the session through the environment its tmux
    # process is created with, and a value decided after that process exists
    # cannot be injected into it. A secret the PLAN later discovers is handled
    # at `release`, honestly, by refusing rather than pretending.
    secrets = _unlock(config, agent, task, vault_prompt)

    runtime = runtime or MachineRuntime()
    workdir = tsk.dir_of(agent, task.id)
    workdir.mkdir(parents=True, exist_ok=True)
    name = f"{agent.id}-{task.id[-4:]}"

    # `A3 is earned, not set.` The registry states what this agent WANTS; the
    # trust ledger decides what it gets. Passing the configured value straight
    # through would make editing one line of JSON a way to hand an agent full
    # autonomy, which is the one thing the ladder exists to prevent.
    # Planning runs at A0: reads allowed, everything else asks. "Plan and stop"
    # is a sentence in a prompt, and a sentence is not a gate — abraham's live
    # run wrote its artefact during planning because nothing held it back. The
    # ceiling does the holding, and `release` raises it.
    ceiling = "A0" if not task.plan_agreed else _effective_ceiling(agent.ceiling)
    started = runtime.start(name, str(workdir), govern=True, ceiling=ceiling,
                            env=secrets, spec=agent.spec)
    if not (started or {}).get("ok"):
        reason = (started or {}).get("reason") or "the session would not start"
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "blocked",
                       "evidence": [reason]}, now=now)
        raise CouldNotStart(reason)

    task.session = {"name": started.get("name", name), "pid": started.get("pid"),
                    "cwd": str(workdir), "ceiling": ceiling,
                    # when it began, so `spend` can report how long it ran
                    # rather than how long ago the task was created
                    "started_at": now(),
                    # what was asked for, beside what was granted: a board that
                    # showed the request would be lying about what is running
                    "ceiling_requested": agent.ceiling,
                    # what ACTUALLY executes the session — the CLI the runtime
                    # drives. Independence is a claim about the engine that did
                    # the work, not the one the worker planned with.
                    "engine": getattr(runtime, "engine", "claude"),
                    "planner": agent.model}
    task.state = tsk.RUNNING
    task = tsk._touch(agent, task, now)

    # The plan is made BETWEEN the worker and the session: if this task has no
    # plan yet, the session is guided to write one and told to stop. Only a task
    # that already has a granted plan is kicked off to do the work.
    plan = tsk.read_plan(config, agent, task)
    if not task.plan_agreed:
        # A plan exists or is seeded, but the session has not had its say. The
        # worker's version goes down as a starting point — anchored to what the
        # owner asked for — and the session is asked to improve it, then stop.
        _seed_plan(config, agent, task)
        task.state = tsk.PLANNING
        task.kickoff_pending = planning_kickoff(config, agent, task)
        task = tsk._touch(agent, task, now)
    else:
        task.kickoff_pending = kickoff(task, plan)
        task = tsk._touch(agent, task, now)
    ledger.append(config, "directives",
                  {"agent": agent.id, "task": task.id, "assigned": True,
                   "session": task.session["name"], "goal": task.goal}, now=now)
    return task


def _effective_ceiling(requested: str) -> str:
    """What the trust ledger actually allows. Fail-safe: if it cannot be read,
    the answer is the requested ceiling capped at A2, never above it."""
    try:
        from ai4science.harness.agents.machine import trust
        return trust.effective_ceiling(requested)
    except Exception:
        return "A2" if str(requested).upper() == "A3" else requested


def _late_secrets(config: Config, agent: Agent, task: tsk.Task) -> list:
    """Secrets the PLAN asks for that the directive never declared."""
    declared = {s.lower() for s in (task.directive or {}).get("requires_secrets") or []}
    plan = tsk.read_plan(config, agent, task)
    if plan is None:
        return []
    wanted = []
    for permission in plan.permissions:
        text = str(permission).lower()
        if "secret" not in text:
            continue
        name = text.replace("read secret", "").replace("secret", "").strip()
        if name and name not in declared:
            wanted.append(name)
    return wanted


def _unlock(config: Config, agent: Agent, task: tsk.Task,
            prompt: Optional[Callable]) -> Dict[str, str]:
    """Ask the vault for every secret this task's directive declared.

    Returns the values for the local session only. They are never written to the
    task record, the plan, or any ledger — the vault ledger records *which*
    secret was asked for and what was decided, and nothing more.
    """
    from ai4science.harness.agents.sarsi import vault

    wanted = list((task.directive or {}).get("requires_secrets") or [])
    if not wanted:
        return {}
    prompt = prompt or _refuse_silently
    out: Dict[str, str] = {}
    for secret in wanted:
        decision = vault.ask(config, agent_id=agent.id, secret=secret,
                             act="read", purpose=task.goal, prompt=prompt,
                             standing_grants=agent.standing_grants)
        if not decision.allowed:
            raise NotReady(decision.reason)
        out[secret] = decision.value or ""
    return out


def _refuse_silently(**_: Any) -> None:
    """No way to reach the owner is not an approval."""
    return None


def _env_key(name: str) -> str:
    return name.upper().replace(".", "_").replace("-", "_")


def planning_kickoff(config: Config, agent: Agent, task: tsk.Task) -> str:
    """Ask the session to **improve the worker's initial plan** — and stop.

    The worker seeds it: the goal, the scope, and the tools and secrets the
    directive declared, in the shape a plan has to take. That anchors the plan
    to what the owner actually asked for, and leaves something usable if the
    session produces nothing. The session has the model and the repo, so it
    sharpens what the worker could only sketch.

    It must stop afterwards. A session that drafts a plan and then does the work
    has done work nobody granted — and what the plan declares is precisely what
    the owner has not yet seen.
    """
    from ai4science.harness.agents.sarsi import workspace as ws

    scope = (task.directive or {}).get("scope") or []
    lines = [
        f"Goal: {task.goal}",
        "",
        # The history, spliced in: a plan written without it repeats every
        # mistake the history records — and asks again for a permission the
        # owner already refused.
        ws.render(config, agent, task),
        "",
        f"FIRST, PLAN — together. I have already written an initial "
        f"{PLAN_FILE} in this folder: the goal, what I know it needs, and the "
        f"shape a plan takes here. It is a sketch, not an instruction.",
        "",
        f"Read it, then improve it in place. Sharpen it with what you can see "
        f"and I cannot:",
        "  - split or reorder the phases so they match the real work;",
        "  - rewrite each `Verified when:` line to name what an independent "
        "verifier must SEE — a file, a count, an exit code — never an intention;",
        "  - add to `## Permissions needed` anything beyond this folder you will "
        "actually need: paths, accounts, network, credentials by name.",
        "",
        "Keep the headings and the `Verified when:` lines: a phase without one "
        "cannot be judged by anyone but you.",
        "",
        "While planning you are at ceiling A0: reading files is allowed, and "
        "every shell command stops for the owner. Look around with your file "
        "tools rather than with `ls`/`cat`, or you will be waiting on an "
        "approval instead of planning. The ceiling rises when the owner "
        "releases the task.",
    ]
    if scope:
        lines += ["", "Scope you may touch: " + ", ".join(scope)]
    lines += ["", "Then STOP and say the plan is ready. The owner reviews it and "
                  "grants what it declares before any of it runs."]
    return "\n".join(lines)


def _seed_plan(config: Config, agent: Agent, task: tsk.Task) -> str:
    """Write the worker's initial plan and remember it, so we can tell later
    whether the session actually engaged with it."""
    from ai4science.harness.agents.sarsi.worker import Directive

    d = task.directive or {}
    directive = Directive(agent_id=agent.id, goal=task.goal,
                          scope=list(d.get("scope") or []),
                          criteria=list(d.get("criteria") or []),
                          requires_secrets=list(d.get("requires_secrets") or []))
    folder = tsk.dir_of(agent, task.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / PLAN_FILE
    # keep a plan the worker already wrote (`sarsi do` seeds one); only draft
    # from scratch when there is nothing there at all
    text = path.read_text() if path.exists() else pl.draft(directive).render()
    path.write_text(text)
    (folder / SEED_FILE).write_text(text)
    return text


#: How many times the first instruction is typed before the owner is told it is
#: not landing. Beyond this a loop is just filling a transcript with copies.
MAX_KICKOFF_TRIES = 3


def deliver_kickoff(config: Config, agent: Agent, task: tsk.Task, *,
                    runtime: Optional[Any] = None, screen: str = "",
                    now=time.time) -> tsk.Task:
    """Hand the session its first instruction, and confirm it actually landed.

    `assign` does not type it: a session started microseconds ago is still
    booting and the text is dropped. But *sending* is not *delivering* either —
    grace's run typed the kickoff while Claude Code was still showing its
    startup banner, the text went nowhere, and the worker spent the rest of the
    run believing the session had been told.

    So it stays pending until a distinctive piece of it is **seen on screen**,
    and is retyped up to `MAX_KICKOFF_TRIES` before the owner is told.
    """
    pending = task.kickoff_pending
    if not pending:
        return task

    marker = _kickoff_marker(pending)
    if marker and marker in (screen or ""):
        task.kickoff_pending = None
        return tsk._touch(agent, task, now)

    if task.kickoff_tries >= MAX_KICKOFF_TRIES:
        task.kickoff_undelivered = True
        return tsk._touch(agent, task, now)

    (runtime or MachineRuntime()).send((task.session or {}).get("name", ""), pending)
    task.kickoff_tries += 1
    return tsk._touch(agent, task, now)


def _kickoff_marker(text: str) -> str:
    """A fragment distinctive enough that seeing it means the session has it."""
    for line in (text or "").splitlines():
        line = line.strip()
        if len(line) > 20:
            return line[:40]
    return (text or "")[:40]


def collect_plan(config: Config, agent: Agent, task: tsk.Task, *,
                 runtime: Optional[Any] = None, session_idle: bool = False,
                 accept_seed: bool = False, now=time.time) -> tsk.Task:
    """Read back the plan the session wrote — never the seed it ignored.

    A plan identical to the worker's seed means the session has not engaged with
    it, and no amount of quiet changes that. The task stays `planning`, visibly,
    until either the session improves the plan or the owner accepts the seed
    deliberately with `accept_seed`.
    """
    if task.state != tsk.PLANNING:
        return task
    path = tsk.dir_of(agent, task.id) / PLAN_FILE
    if not path.exists():
        return task                       # still writing it

    seed_path = tsk.dir_of(agent, task.id) / SEED_FILE
    untouched = seed_path.exists() and seed_path.read_text() == path.read_text()
    if untouched and not accept_seed:
        # A quiet session is NOT a session that has planned. social's run went
        # to `ready` holding a plan that still said "(provisional — no criterion
        # was given)" because a quiet pass adopted the seed on the agent's own
        # say-so. If the session will not plan, that is the owner's call.
        return task

    try:
        plan = pl.parse(path.read_text())
    except pl.BadPlan as e:
        # Not accepted quietly: a phase with no criterion leaves the agent that
        # did the work as the only grader of it.
        (runtime or MachineRuntime()).send(
            (task.session or {}).get("name", ""),
            f"That plan cannot be used: {e}\n"
            f"Every phase must end in a `Verified when:` line naming what an "
            f"independent verifier must see. Fix {PLAN_FILE} and stop again.")
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "plan-rejected",
                       "evidence": [str(e)]}, now=now)
        return task

    unchanged = untouched
    task = tsk.adopt_plan(config, agent, task, plan, now=now)
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": "planned",
                   # a thin seed must never be mistaken for a considered plan
                   "unchanged": unchanged,
                   "evidence": [f"{len(plan.phases)} phase(s)"
                                + (" — still the worker's seed, the session did "
                                   "not improve it" if unchanged else "")],
                   "needed_and_missing": list(task.awaiting)}, now=now)
    return task


def release(config: Config, agent: Agent, task: tsk.Task, *,
            runtime: Optional[Any] = None, vault_prompt: Optional[Callable] = None,
            now=time.time) -> tsk.Task:
    """Let the session work its plan — only once the owner has granted.

    `VLT` sits here rather than at `assign`: the plan is what declares which
    secrets are needed, so it has to exist and be granted first. A denied secret
    stops the task before any work begins, and names the secret.
    """
    if task.awaiting:
        raise NotReady("this task is still waiting on a grant: "
                       + ", ".join(task.awaiting))
    # A secret the plan declared that the directive did not: it cannot be
    # delivered into a session that is already running, so say so rather than
    # start work that will fail for a reason nobody can see.
    late = _late_secrets(config, agent, task)
    if late:
        raise NotReady(
            "the plan declares secrets the task was not started with: "
            + ", ".join(late)
            + f" — re-run it with --secret {late[0]} so the session is created "
              f"with it, rather than having it pushed in afterwards")
    plan = tsk.read_plan(config, agent, task)
    task = tsk.start(config, agent, task, now=now)
    if task.state != tsk.RUNNING:
        return task

    # The owner has seen the plan and granted what it declared, so the session
    # may now do more than read. Raised only to what this agent has EARNED.
    raised = _effective_ceiling(agent.ceiling)
    rt = runtime or MachineRuntime()
    try:
        rt.set_ceiling((task.session or {}).get("name", ""), raised)
    except Exception:
        pass
    if task.session:
        task.session["ceiling"] = raised
        task = tsk._touch(agent, task, now)
    rt.send((task.session or {}).get("name", ""), kickoff(task, plan))
    return task


def stop(config: Config, agent: Agent, task: tsk.Task, *,
         runtime: Optional[Any] = None, archive: bool = False,
         now=time.time) -> tsk.Task:
    """Stop a task and take its session with it.

    A stopped task whose tmux session keeps running is the worst of both: the
    board says nothing is happening while something is, and the next `run` on
    that task starts a second session against the same folder.

    Killing the session is best-effort by design — if tmux is gone, or the
    session was already killed by hand, the task still stops. The owner asked
    for it stopped; refusing to record that because the cleanup failed would
    leave the board lying in the other direction.
    """
    runtime = runtime or MachineRuntime()
    name = (task.session or {}).get("name")
    if name:
        try:
            runtime.stop(name)
        except AttributeError:
            # A runtime that cannot stop is a caller's mistake, not a machine
            # failure: it leaves a live terminal behind a stopped task. Fall
            # back to the real one rather than silently leaving it running.
            try:
                MachineRuntime().stop(name)
            except Exception:
                pass
        except Exception:
            pass                      # the record matters more than the cleanup
        # Keep what it cost. Clearing the record outright took the working
        # directory with it, and with the directory went the transcript — so a
        # task became unmeasurable the moment it was tidied away, and the spend
        # figure fell as work FINISHED. That is the one thing it must not do.
        past = list(task.past_sessions or [])
        past.append(dict(task.session or {}, ended_at=now()))
        task.past_sessions = past
        task.session = None
    task = (tsk.archive if archive else tsk.turn_off)(config, agent, task, now=now)
    return task


def _verify_phase(config: Config, agent: Agent, task: tsk.Task, *,
                  verifier: Callable[..., Dict[str, Any]], evidence: str,
                  engine: Optional[str], index: int, now) -> tsk.Task:
    """Judge ONE phase against ONE criterion.

    Judging a phase against every criterion would make "phase 1 passed" mean
    "everything passed", and the phase number would be decoration on a
    task-level verdict.
    """
    criteria = list(task.criteria or [])
    if index < 0 or index >= len(criteria):
        raise IndexError(f"{task.id} has {len(criteria)} phase(s); there is no "
                         f"phase {index + 1}")

    verdict = dict(verifier(goal=task.goal, criteria=[criteria[index]],
                            evidence=evidence) or {})
    verdict["engine"] = engine or "unknown"
    ran_it = (task.session or {}).get("engine") or agent.model or ""
    verdict["independent"] = bool(engine and engine != ran_it)
    verdict["criteria"] = [criteria[index]]
    verdict["phase"] = index + 1

    from ai4science.harness.agents.sarsi import verifier as vf

    if not vf.was_judged(verdict):
        # Nothing judged it, so nothing is recorded ABOUT the phase — an
        # unrecorded phase is incomplete, which is the honest reading.
        task.verdict = verdict
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "unverified",
                       "verdict": verdict, "evidence": [evidence[:500]]}, now=now)
        return tsk._touch(agent, task, now)

    task = tsk.record_phase(config, agent, task, index, verdict, now=now)
    task.verdict = verdict
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id,
                   "state": "verified" if vf.is_pass(verdict) else "failed",
                   "verdict": verdict, "evidence": [evidence[:500]]}, now=now)

    if tsk.earliest_incomplete(task) is None:
        # Every phase has its own PASS. The task-level verdict says how it was
        # reached, so a reader can tell a whole-task judgment from a sum of
        # per-phase ones.
        done = len(criteria)
        task = tsk.finish(config, agent, task, verdict={
            "state": "PASS",
            "why": f"every phase was verified on its own: {done} of {done} "
                   f"phase(s) passed",
            "engine": verdict["engine"],
            "independent": verdict["independent"],
            "criteria": criteria}, now=now)
        return task
    return tsk._touch(agent, task, now)


def who_drives(task: tsk.Task) -> str:
    """The ladder, in one place. The owner is the top of it."""
    return "owner" if task.steering_paused else "worker"


def guide(config: Config, agent: Agent, task: tsk.Task, instruction: str, *,
          runtime: Optional[Any] = None, by_owner: bool = False,
          now=time.time) -> tsk.Task:
    """Steer a session by hand — the worker guiding it, or the owner through it.

    The owner's guidance always goes through, including while they hold the
    wheel: it is their word arriving on their own session. The **worker's**
    guidance stands down entirely when they do.
    """
    if not by_owner and who_drives(task) == "owner":
        raise OwnerHasTheWheel(
            f"you have the wheel on {task.id}; {agent.id} is standing by. "
            f"Hand it back with /resume {task.id}.")
    (runtime or MachineRuntime()).send((task.session or {}).get("name", ""),
                                       instruction)
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id,
                   "state": "guided-by-owner" if by_owner else "guided",
                   "evidence": [instruction[:200]]}, now=now)
    return task


def kickoff(task: tsk.Task, plan: Optional[pl.Plan]) -> str:
    """What the session is told first: the goal, its plan file, and the phase to
    work. Never the conversation that produced them."""
    lines = [f"Goal: {task.goal}"]
    if plan is not None and task.plan_version:
        lines.append(f"Your plan is {task.plan_version}.md in this folder. "
                     f"Work its earliest incomplete phase.")
        # The real number: the first phase without a PASS of its own. A phase is
        # complete when the VERIFIER said so about that phase — the session
        # saying it is finished does not move this.
        index = tsk.earliest_incomplete(task) or 0
        done = [p.title for i, p in enumerate(plan.phases)
                if tsk.phase_passed(task, i)]
        if done:
            lines.append("Already verified, do not redo: " + "; ".join(done))
        if index < len(plan.phases):
            here = plan.phases[index]
            lines.append(f"Earliest incomplete phase: {here.title}")
            lines.append(f"Verified when: {here.verified_when}")
    lines.append("Report what you did with the evidence for it. "
                 "An independent verifier decides whether the goal is met.")
    return "\n".join(lines)


def verify(config: Config, agent: Agent, task: tsk.Task, *,
           verifier: Callable[..., Dict[str, Any]], evidence: str = "",
           engine: Optional[str] = None, runtime: Optional[Any] = None,
           phase: Optional[int] = None, now=time.time) -> tsk.Task:
    """Ask the verifier, and act on what it says.

    On PASS the task is verified and the verdict recorded. On FAIL the reason is
    **fed back into the session** as the next instruction rather than merely
    logged — a reason that only reaches a log steers nothing.
    """
    if task.plan_stale:
        # The owner drove this session by hand, so the plan no longer describes
        # what happened. Judging against the goal alone would silently answer a
        # WEAKER question than the one the owner set, and report the answer as
        # though it were the one they asked — which is how a false PASS gets
        # recorded. Refusing, and saying how to clear it, is the honest move.
        from ai4science.harness.agents.sarsi import verifier as _vf
        task.verdict = dict(_vf._unverified(
            "the plan is stale: you drove this session directly, so it no "
            "longer describes what happened. Rewrite it first — "
            f"/edit {task.id} <phase#> <criterion> — then ask again."))
        task.verdict.update({"engine": engine or "unknown",
                             "independent": False,
                             "criteria": list(task.criteria or [])})
        task.state = tsk.RUNNING
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "not-judged",
                       "evidence": ["the plan is stale"]}, now=now)
        return tsk._touch(agent, task, now)

    if phase is not None:
        return _verify_phase(config, agent, task, verifier=verifier,
                             evidence=evidence, engine=engine, index=phase,
                             now=now)

    criteria = list(task.criteria or [])
    verdict = dict(verifier(goal=task.goal, criteria=criteria, evidence=evidence) or {})
    verdict["engine"] = engine or "unknown"
    # A different engine is the cheapest independence there is; when it is the
    # same one, say so rather than claiming an independence we do not have.
    # Compared against the engine that RAN the session: the live run recorded
    # `independent: true` for a claude-judged, claude-executed task because the
    # worker's planning model happened to be a different string.
    ran_it = (task.session or {}).get("engine") or agent.model or ""
    verdict["independent"] = bool(engine and engine != ran_it)
    verdict["criteria"] = criteria

    from ai4science.harness.agents.sarsi import verifier as vf

    if not vf.was_judged(verdict):
        # Nothing judged this. It is not a pass, and it is not a finding about
        # the work either — so nothing is steered into the session. Telling it
        # to "address" an absent verifier is a correction nobody made about a
        # problem it cannot fix.
        task.verdict = verdict
        task.state = tsk.RUNNING
        task = tsk._touch(agent, task, now)
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "unverified",
                       "verdict": verdict, "steered": False,
                       "evidence": [evidence[:500]]}, now=now)
        return task

    if vf.is_pass(verdict):
        task = tsk.finish(config, agent, task, verdict=verdict, now=now)
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "verified",
                       "verdict": verdict, "evidence": [evidence[:500]]}, now=now)
        return task

    task.verdict = verdict
    task.state = tsk.RUNNING
    task = tsk._touch(agent, task, now)
    why = verdict.get("why") or "the verifier was not satisfied"
    steered = False
    if task.session:
        try:
            (runtime or MachineRuntime()).send(
                task.session["name"],
                f"The independent verifier says this is not done yet: {why}\n"
                f"Address that specifically, then report the evidence again.")
            steered = True
        except Exception:
            steered = False
    # A reason that reached no session steered nothing. Record that rather than
    # let the log imply a correction everyone assumes was delivered.
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": "running",
                   "verdict": verdict, "steered": steered,
                   "evidence": [evidence[:500]]}, now=now)
    return task


def answer(config: Config, agent: Agent, task: tsk.Task) -> str:
    """What the owner is told — **at what authority the claim stands.**

    In a fleet, "it worked" is an incomplete sentence.
    """
    session = (task.session or {}).get("name") or "no session"
    if task.state == tsk.VERIFIED and (task.verdict or {}).get("state") == PASS:
        independence = "" if (task.verdict or {}).get("independent") \
            else " (judged by the same engine that did the work)"
        return (f"verified — {task.goal}\n"
                f"session {session}, verdict {PASS}{independence}")
    verdict = task.verdict or {}
    if str(verdict.get("state", "")).upper() == "UNVERIFIED":
        # distinct from "in progress": the work may be done and nobody looked
        return (f"not judged — {task.goal}\n"
                f"session {session}: {verdict.get('why', '')}")
    if task.state == tsk.RUNNING:
        return f"recorded — {task.goal} is in progress in session {session}"
    return f"I think — {task.goal} is {task.state} in session {session}"
