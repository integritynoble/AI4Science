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
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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


class NoSession(Exception):
    """There is nowhere to deliver it, so it was not delivered."""


class NotDrivable(Exception):
    """Typing at an interface this loop cannot read. The owner delivers it."""


class OwnerHasTheWheel(Exception):
    """The owner is driving. The worker stands down — top of the ladder."""


class MachineRuntime:
    """The real one: the machine agent's tmux session control."""

    #: what actually executes the session, for the independence comparison
    engine = "claude"

    def start(self, name: str, cwd: str, *, govern: bool, ceiling: str,
              env: Optional[Dict[str, str]] = None,
              spec: str = "claude-code",
              writable: Optional[List[str]] = None) -> Dict[str, Any]:
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
        # The plan's working directory reaches the sandbox as a launch flag, so
        # widening it needs a NEW session: an agent that rewrites its own plan
        # mid-run does not thereby gain a directory. Quoted — a declared path
        # may contain spaces, and this string becomes a shell command.
        import shlex
        extra = "".join(f" --writable {shlex.quote(str(w))}"
                        for w in (writable or []) if w)
        return sessions.start_session(
            name, cwd, govern=govern, ceiling=ceiling,
            claude_bin=f"ai4science chat --mode {spec}{extra}")

    def send(self, name: str, text: str, *, _send=None) -> Dict[str, Any]:
        """Type one instruction into a session — as ONE keystroke stream.

        `tmux send-keys -l` sends the literal text *including its newlines*,
        and a newline in a TUI input box is a submit. So a multi-line brief was
        never typed, it was submitted in FRAGMENTS: `Goal: …` went alone as a
        prompt, and the rest arrived while the session was busy answering it.
        The session never received the brief, its first line scrolled out of
        the visible pane, the delivery check never saw its marker — and the
        loop reported `undelivered` about a session it had fragmented itself.

        Seen twice: as that report on `work`, and in my own hands — every brief
        delivered by hand this session was written `.replace("\\n", " ")`,
        which is this rule, applied manually and never fed back into the code.
        """
        from ai4science.harness.agents.machine import sessions
        # Newlines to spaces, not stripped: the words all still arrive, in one
        # submission, which is what "tell the session this" has always meant.
        one_line = " ".join((text or "").split("\n"))
        return (_send or sessions.send_to_session)(name, one_line)

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
    home = tsk.dir_of(agent, task.id)
    home.mkdir(parents=True, exist_ok=True)
    # Where the session STANDS. `--workdir` says where the work happens, and a
    # session standing five levels away from it addressed its own target as
    # `../../../../../live-brief/report.md` — a path nothing checked, invented
    # because the flag it was given moved the evidence root and not the cwd.
    #
    # Not created if it is missing: a typo would become a new empty directory
    # that the session then truthfully reports as an empty project. The task
    # folder is the honest fallback, and the owner sees the name they meant.
    workdir = home
    declared = (task.work_root or "").strip()
    if declared:
        try:
            candidate = Path(declared).expanduser().resolve()
            if candidate.is_dir():
                workdir = candidate
        except OSError:
            pass
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
    # Everything the PLAN declared this task may change, beyond the folder the
    # session runs in. `blast` already treats these as permitted; the sandbox
    # refusing them did not stop the write, it pushed it into a `bash` heredoc
    # that `blast` cannot read. Two boundaries that disagree are one boundary
    # and one blind spot.
    # The TASK FOLDER is in here whenever the session is standing somewhere
    # else: `plan0.md` lives there and the planning step exists to edit it, so a
    # sandbox permitting only the cwd would refuse the one write it is for.
    writable = [str(p) for p in tsk.evidence_roots(agent, task)
                if str(p) != str(workdir)]
    writable += [str(p) for p in (task.may_touch or [])]
    started = runtime.start(name, str(workdir), govern=True, ceiling=ceiling,
                            env=secrets, spec=agent.spec,
                            writable=writable or None)
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
    # A count of failures belongs to the session that failed. Live: a task
    # burned all three tries against a session `start_session` had reported and
    # never actually started, and the restart inherited the count — so the loop
    # declared the brief undeliverable before one keystroke reached the session
    # that existed. Carrying it forward reports the past as the present.
    task.kickoff_tries = 0
    task.kickoff_undelivered = False
    task.kickoff_unreachable = False
    task.acts_at_kickoff = None
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
        task.kickoff_pending = kickoff(task, plan, agent)
        task = tsk._touch(agent, task, now)
    ledger.append(config, "directives",
                  {"agent": agent.id, "task": task.id, "assigned": True,
                   "session": task.session["name"], "goal": task.goal}, now=now)
    return task


def _note_drift(agent: Agent, task: tsk.Task, verdict: Dict[str, Any],
                drifted: List[int]) -> Dict[str, Any]:
    """Say on the verdict that the file has moved since it was released.

    Judged is not the same as unnoticed. A PASS carrying nothing would leave
    the owner reading a verdict against a criterion the file no longer shows,
    and `sarsi plan` renders the file — so the two would disagree in front of
    them with no explanation. The note travels ON the verdict rather than only
    in `why`, because a verdict is the thing that gets read.
    """
    if not drifted:
        return verdict
    which = ", ".join(str(i + 1) for i in drifted)
    verdict["why"] = (
        f"{verdict.get('why', '')}\n\n"
        f"(Judged against what you released. {task.plan_version}.md has since "
        f"changed at phase {which} — the session edited its own copy. To make "
        f"the file the standard instead: sarsi adopt {agent.id} {task.id}, "
        f"which clears the verdicts of the phases that changed.)").strip()
    verdict["plan_drifted"] = list(drifted)
    return verdict


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


def _plan_reference(agent: Optional[Agent], task: tsk.Task) -> str:
    """How to name the plan file to a session, given where it is standing.

    Relative when the session is IN the task folder — no absolute paths where a
    short relative one is correct. Absolute the moment it is not, because the
    plan stays with the task: `plan0.md` is the record and does not follow the
    session into a project directory that may be shared, versioned, or someone
    else's.
    """
    name = f"{task.plan_version or 'plan0'}.md"
    if agent is None:
        # `kickoff` takes the agent optionally and callers that only want the
        # goal and the phase pass none. Without it the task folder cannot be
        # resolved, so the old relative wording is the honest answer — an
        # absolute path guessed from a task id would be worse than a short one.
        return f"{name} in this folder"
    home = tsk.dir_of(agent, task.id)
    cwd = (task.session or {}).get("cwd")
    if not cwd:
        declared = (task.work_root or "").strip()
        try:
            cwd = str(Path(declared).expanduser().resolve()) if declared else None
        except OSError:
            cwd = None
    if not cwd or str(cwd) == str(home) or str(cwd) == str(home.resolve()):
        return f"{name} in this folder"
    return str(home / name)


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
    # The plan lives with the TASK; the session may be standing in the declared
    # working directory instead. "in this folder" was true only while those were
    # the same place — a session told to read a file that is not where it stands
    # reads nothing and plans from the goal alone, and is then judged against
    # criteria the owner never reviewed.
    where = _plan_reference(agent, task)
    lines = [
        f"Goal: {task.goal}",
        "",
        # The history, spliced in: a plan written without it repeats every
        # mistake the history records — and asks again for a permission the
        # owner already refused.
        ws.render(config, agent, task),
        "",
        f"FIRST, PLAN — together. I have already written an initial "
        f"plan at {where}: the goal, what I know it needs, and the "
        f"shape a plan takes here. It is a sketch, not an instruction.",
        "",
        f"Read it, then improve it in place. Sharpen it with what you can see "
        f"and I cannot:",
        "  - split or reorder the phases so they match the real work;",
        "  - rewrite each `Verified when:` line so it can be checked from the "
        "FILES ALONE. The verifier is given the files under the working "
        "directory and this task's folder, and nothing else: it has no "
        "transcript, sees none of your tool calls, and your narration reaches "
        "it marked `not evidence`. So `the transcript contains a Read of "
        "x.csv` is not a hard criterion, it is an impossible one — no verdict "
        "can ever be reached on it. Write what a stranger opening the folder "
        "could confirm: a named file exists, its text contains a literal "
        "string, a count matches, an exit code is 0. Never an intention, and "
        "never anything only you can see;",
        "  - add to `## Permissions needed` anything beyond where you are "
        "standing that you will actually need: paths, accounts, network, "
        "credentials by name.",
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
                    acts=None, now=time.time) -> tsk.Task:
    """Hand the session its first instruction, and confirm it actually landed.

    Never for a spec this loop cannot read. Typing at an interface it does not
    understand is not briefing: on the ai4science TUI a brief full of `j`s and
    `k`s walked a menu cursor onto "No, exit" and killed the session.

    `assign` does not type it: a session started microseconds ago is still
    booting and the text is dropped. But *sending* is not *delivering* either —
    grace's run typed the kickoff while Claude Code was still showing its
    startup banner, the text went nowhere, and the worker spent the rest of the
    run believing the session had been told.

    So it stays pending until a distinctive piece of it is **seen on screen**,
    and is retyped up to `MAX_KICKOFF_TRIES` before the owner is told.
    """
    if not drivable(agent.spec):
        # Reported, not typed. The owner briefs an attended session by hand.
        return task

    pending = task.kickoff_pending
    if not pending:
        return task

    # Two confirmations, and the second is why the first is not enough.
    #
    # The MARKER is a fragment of the brief seen on screen. Cheap, immediate,
    # and it expires: it scrolls away the moment the session starts working, so
    # the evidence of delivery is destroyed by delivery succeeding. Live, four
    # `briefing` passes in a row at a session that was busy carrying the brief
    # out, retyping what it already had.
    marker = _kickoff_marker(pending)
    if marker and marker in (screen or ""):
        task.kickoff_pending = None
        task.acts_at_kickoff = None
        return tsk._touch(agent, task, now)

    # ACTING does not expire. A session that has used a tool since the brief was
    # typed received an instruction — nothing else was typed at it, and at the
    # A0 planning ceiling nothing else prompts it. The count is taken WHEN THE
    # BRIEF IS TYPED, not from zero: a session that ran fifty tools before being
    # briefed has not thereby received the brief.
    if task.acts_at_kickoff is not None:
        since = _steps_so_far(task, acts)
        if since is not None and since > task.acts_at_kickoff:
            task.kickoff_pending = None
            task.acts_at_kickoff = None
            return tsk._touch(agent, task, now)

    # A screen that cannot take text is not typed at. Keystrokes into a modal
    # are discarded and the Enter answers whichever option is highlighted — the
    # loop would be voting on a permission prompt with the brief. The work
    # branch of the operator has guarded this since it was written; the
    # PLANNING branch, which is where every task starts, did not, so this lives
    # here rather than at one call site and applies to both.
    from ai4science.harness.agents.sarsi.operator import _busy, _gate
    if _busy(screen or "") or _gate(screen or "") is not None:
        # No try is spent: the count is of attempts to DELIVER, and a pass that
        # correctly declined to type made no attempt. Charging it walks the
        # owner toward "the session is refusing its brief" about a session that
        # has not been asked.
        return task

    if task.kickoff_tries >= MAX_KICKOFF_TRIES:
        task.kickoff_undelivered = True
        return tsk._touch(agent, task, now)

    out = (runtime or MachineRuntime()).send(
        (task.session or {}).get("name", ""), pending) or {}
    if not out.get("ok", True):
        # The keystrokes never reached tmux — there is no such session. That is
        # not the session declining its brief, and charging a try for it walks
        # the owner to "the session is not taking its brief" about a session
        # that is not there. Live: the pane was gone, every send returned
        # ok:False, the result was discarded, and three tries were counted.
        task.kickoff_unreachable = True
        return tsk._touch(agent, task, now)
    task.kickoff_unreachable = False
    # What the transcript held at the moment it was typed. `None` when it could
    # not be read, and that stays None rather than becoming 0 — an unreadable
    # transcript treated as "no acts yet" would confirm delivery on the next
    # pass from no evidence at all.
    task.acts_at_kickoff = _steps_so_far(task, acts)
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
        if not drivable(agent.spec):
            # Same keystrokes, same unknown screen. The task stays `planning`
            # either way, which is what the owner acts on.
            return task
        (runtime or MachineRuntime()).send(
            (task.session or {}).get("name", ""),
            f"That plan cannot be used: {e}\n"
            f"Every phase must end in a `Verified when:` line that can be "
            f"checked FROM THE FILES ALONE. The verifier is given the files "
            f"under the working directory and this task's folder and nothing "
            f"else — no transcript, none of your tool calls, and your "
            f"narration reaches it marked `not evidence`. Fix {PLAN_FILE} and "
            f"stop again.")
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
            acts: Optional[Callable] = None, now=time.time) -> tsk.Task:
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
    # This call IS the boundary between planning and work — it is what raises
    # the ceiling from A0. Marking it here is what lets the declared budget
    # cover the WORK: without the mark, a task that spent its steps planning
    # arrives at its goal with nothing left, which is what happened live.
    task.steps_before_work = _steps_so_far(task, acts)
    task.work_started_at = float(now())
    task = tsk._touch(agent, task, now)

    if drivable(agent.spec):
        # Quiet, like `deliver_kickoff`: raising would make `release` fail
        # outright on an attended agent, and the owner briefs one by hand.
        rt.send((task.session or {}).get("name", ""), kickoff(task, plan, agent))
    return task


def _steps_so_far(task: tsk.Task, acts=None) -> Optional[int]:
    """What planning spent, or None when it cannot be read.

    None rather than 0: an unreadable count recorded as zero would charge the
    work for every planning step, which is the bug this mark exists to fix.
    """
    cwd = (task.session or {}).get("cwd")
    if not cwd:
        return None
    from ai4science.harness.agents.sarsi import blast
    try:
        return len((acts or blast.acts_of)(cwd))
    except Exception:
        return None


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
    # Written BEFORE the session is closed: once the terminal is gone the
    # record is all there is, and this is the moment it is worth having.
    try:
        from ai4science.harness.agents.sarsi import handoff as _ho
        _ho.write(config, agent, task)
    except Exception:
        pass                          # a handoff that cannot be written must
                                      # not stop the task from stopping

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
    verdict = _note_drift(agent, task, verdict,
                          tsk.criteria_drift(agent, task))
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

    Never at a spec this loop cannot read, whoever is speaking. `retry`,
    `answer`, `steer` and a goal change all arrive here, and all four are prose
    typed at a screen: on the ai4science TUI that prose is menu keystrokes, and
    one option is always "No, exit". `by_owner` is not an exemption — the
    hazard is the screen, not the author, and two of the four callers are the
    owner by definition.
    """
    name = (task.session or {}).get("name") or ""
    if not name:
        # Before the interface question, because it is a different fact: not
        # *may we type here* but *there is nowhere to type*. Reported as
        # "attach to ?" it sent the owner to a terminal that does not exist,
        # and on a drivable agent it was quieter and worse — the text went to
        # the empty session name and the CLI said "sent to ?", a delivery
        # nobody received, reported as made.
        raise NoSession(
            f"{task.id} has no session, so there is nowhere to deliver this. "
            f"Start one with `sarsi run {agent.id} {task.id}` first.")
    if not drivable(agent.spec):
        # Refused, not silently skipped: `deliver_kickoff` returns quietly
        # because the loop calls it every pass, but these are commands somebody
        # ran, and a quiet no-op tells them it landed. They are the delivery
        # mechanism now, so hand them the text and where to put it.
        raise NotDrivable(
            f"{agent.id} runs the {agent.spec!r} interface, which this loop "
            f"cannot read — typing at it is keystrokes at an unknown screen, "
            f"and on a menu one option is always the worst one. Deliver it "
            f"yourself:\n\n"
            f"  tmux attach -t {name}\n\n"
            f"{instruction}")
    if not by_owner and who_drives(task) == "owner":
        raise OwnerHasTheWheel(
            f"you have the wheel on {task.id}; {agent.id} is standing by. "
            f"Hand it back with /resume {task.id}.")
    (runtime or MachineRuntime()).send(name, instruction)
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id,
                   "state": "guided-by-owner" if by_owner else "guided",
                   "evidence": [instruction[:200]]}, now=now)
    return task


def kickoff(task: tsk.Task, plan: Optional[pl.Plan],
            agent: Optional[Agent] = None) -> str:
    """What the session is told first: the goal, its plan file, and the phase to
    work. Never the conversation that produced them."""
    lines = [f"Goal: {task.goal}"]
    if plan is not None and task.plan_version:
        lines.append(f"Your plan is {_plan_reference(agent, task)}. "
                     f"Work its earliest incomplete phase.")
        # The real number: the first phase without a PASS of its own. A phase is
        # complete when the VERIFIER said so about that phase — the session
        # saying it is finished does not move this.
        # `None` means every phase has passed. `None or 0` would collapse that
        # to phase 0 — and a finished task would be pointed back at its first
        # phase in the same breath as being told not to redo it.
        index = tsk.earliest_incomplete(task)
        done = [p.title for i, p in enumerate(plan.phases)
                if tsk.phase_passed(task, i)]
        if done:
            lines.append("Already verified, do not redo: " + "; ".join(done))
        if index is None:
            lines.append("Every phase has been verified. Do not start again — "
                         "report what is there and let the verifier judge the "
                         "task as a whole.")
        elif index < len(plan.phases):
            here = plan.phases[index]
            lines.append(f"Earliest incomplete phase: {here.title}")
            lines.append(f"Verified when: {here.verified_when}")
    if agent is not None:
        # What other agents published. The design has reading happen at PLAN
        # time, and that is where the workspace is spliced in — but an owner who
        # sharpens a criterion sets `plan_agreed`, the planning brief is never
        # sent, and the facts vanish with it. Two good rules interacting badly:
        # the single highest-leverage thing an owner can do was stripping the
        # session of everything the fleet had learned. So the facts ride here
        # too, labelled, and still only for an agent that was granted them.
        from ai4science.harness.agents.sarsi import shared as _shared
        facts = _shared.render_for(agent)
        if facts:
            lines.append(facts)

        # The host facts every session would otherwise rediscover. Told, rather
        # than bumped into.
        from ai4science.harness.agents.sarsi import rules as _rules
        house = _rules.render(None, agent)
        if house:
            lines.append(house)

    # An earlier session's handoff, when there is one. `agent` is needed to
    # find the task folder; without it this simply says nothing rather than
    # guessing at a path.
    if agent is not None:
        from ai4science.harness.agents.sarsi import handoff as _ho
        if _ho.exists(agent, task):
            lines.append("An earlier session ended here: read HANDOFF.md in "
                         "this folder before starting. It says what was "
                         "already verified — do not redo it.")
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
    drifted = tsk.criteria_drift(agent, task)
    # Refused only when nobody has said which of the two is meant. Two owner
    # acts say it, and both are exemptions:
    #
    #   * the owner AUTHORED the criteria (`plan_owner_edited`), or
    #   * the owner RELEASED the task — they read the plan, granted each
    #     permission it declared, and raised the ceiling, all against the
    #     standard in the record. A file edited afterwards is not a competing
    #     reading of an open question, it is the session's working copy moving
    #     after the question was answered.
    #
    # Sessions revise their plan mid-work as a matter of course, so without the
    # second exemption the refusal fires on most tasks — and what it asks the
    # owner to do to unblock is ADOPT WHATEVER THE SESSION JUST WROTE. A gate
    # that is habitually rubber-stamped is worse than no gate: it launders the
    # session's rewrite as the owner's decision. Judging against the record
    # denies the session its own bar without stopping to ask.
    released = task.work_started_at is not None
    if drifted and not task.plan_owner_edited and not released:
        # `sarsi plan` renders the file while this judges the copy taken at
        # attach time, so an owner sharpening a criterion in the file was
        # judged against the one they replaced — live, that produced two FAILs
        # whose reasons were both true of a criterion nobody was looking at.
        #
        # Refused rather than resolved: the plan file lives in the session's
        # own working directory, so "the file wins" would let the agent being
        # judged restate the question and drop the verdict that failed it.
        # Which criterion is meant is genuinely unknown, so UNVERIFIED.
        from ai4science.harness.agents.sarsi import verifier as _vf
        which = ", ".join(str(i + 1) for i in drifted)
        task.verdict = dict(_vf._unverified(
            f"{task.plan_version}.md no longer matches the criteria this task "
            f"was attached with — phase {which} reads differently. Judging "
            f"would answer one of two questions without saying which. Take the "
            f"file as the standard with `sarsi adopt {agent.id} {task.id}`, "
            f"which clears the verdicts of the phases that changed."))
        return tsk._touch(agent, task, now)

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
    verdict = _note_drift(agent, task, verdict, drifted)
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
    # Not at an interface this loop cannot read. `check` on an attended agent
    # was typing this paragraph at whatever screen happened to be showing —
    # the same hazard `guide` refuses, one command earlier and unnoticed. Quiet
    # here rather than raised: judging is not steering, and a verdict must not
    # be lost because it could not also be delivered. `steered` stays False,
    # which the ledger below already reports honestly.
    if task.session and drivable(agent.spec):
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


def answer(config: Config, agent: Agent, task: tsk.Task, *,
           fresh: bool = True) -> str:
    """What the owner is told — **at what authority the claim stands.**

    In a fleet, "it worked" is an incomplete sentence. So is "it was not
    judged", when the run being reported did not judge it: `supervise` closes
    by printing this, and printed a verdict recorded an HOUR earlier in the
    same words it would use for one from just now. Live, that read as the run
    refusing on a stale plan while a direct check said the plan was settled
    and `check` judged it normally — nothing disagreed, and I hunted a drift
    bug that was not there.

    `fresh=False` says this verdict is the task's STANDING one and predates
    the run being reported. It changes the sentence, never the verdict.
    """
    # No `or "no session"`: filling the hole with a phrase that reads like a
    # name produced `session no session, verdict PASS` on a task whose session
    # had already been released. Where there is no session there is no session
    # clause — the sentence is about the verdict either way.
    name = (task.session or {}).get("name") or ""
    if not fresh and (task.verdict or {}).get("state"):
        verdict = task.verdict or {}
        return (f"nothing in this run judged {task.id}. Its standing verdict, "
                f"recorded earlier, is {verdict.get('state')} — "
                f"{verdict.get('why') or 'no reason given'}")
    if task.state == tsk.VERIFIED and (task.verdict or {}).get("state") == PASS:
        independence = "" if (task.verdict or {}).get("independent") \
            else " (judged by the same engine that did the work)"
        where = f"session {name}, " if name else ""
        return (f"verified — {task.goal}\n"
                f"{where}verdict {PASS}{independence}")
    verdict = task.verdict or {}
    if str(verdict.get("state", "")).upper() == "UNVERIFIED":
        # distinct from "in progress": the work may be done and nobody looked
        where = f"session {name}: " if name else ""
        return (f"not judged — {task.goal}\n"
                f"{where}{verdict.get('why', '')}")
    if task.state == tsk.RUNNING:
        where = f" in session {name}" if name else ""
        return f"recorded — {task.goal} is in progress{where}"
    where = f" in session {name}" if name else ""
    return f"I think — {task.goal} is {task.state}{where}"
