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

from ai4science.harness.agents.sarsi import ledger, memory, plan as pl, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config
from ai4science.harness.agents.sarsi.worker import NotAWorker

PASS = "PASS"
FAIL = "FAIL"
PLAN_FILE = "plan0.md"
#: A copy of the worker's seed, so "did the session engage?" is answerable.
SEED_FILE = ".plan-seed.md"


class NotReady(Exception):
    """The task is not ready to be assigned — and this says what it is waiting for."""


class CouldNotRelease(Exception):
    """The ceiling would not raise, so the task was not released.

    Reported rather than recorded: the hook reads the LIVE supervisor record,
    so a raise that failed leaves the session at A0 while this record would
    have claimed the new ceiling — the board, `attention` and `agents` all
    showing the owner a thing that is not true about the one field the ladder
    rests on.
    """


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
        if spec == "opencode":
            # OpenCode has no PreToolUse hook mechanism: `govern` is a
            # Claude-Code-only boundary, and wiring it would either fail or
            # write a hook the engine never reads. OpenCode sessions start
            # ungoverned — the ceiling is recorded for the supervisor, not
            # enforced by a hook.
            self.engine = "opencode"
            return sessions.start_session(name, cwd, govern=False,
                                          ceiling=ceiling, claude_bin="opencode")
        # `claude-code` is Claude Code itself; anything else runs through the
        # ai4science harness in that mode.
        binary = "claude" if spec == "claude-code" else None
        if binary:
            # `writable` reaches Claude Code through the governance hook rather
            # than a launch flag — it has no `--writable`, and the hook is the
            # only boundary a claude-code session actually has.
            self.engine = "claude"
            return sessions.start_session(name, cwd, govern=govern,
                                          ceiling=ceiling, writable=writable)
        # The plan's working directory reaches the sandbox as a launch flag, so
        # widening it needs a NEW session: an agent that rewrites its own plan
        # mid-run does not thereby gain a directory. Quoted — a declared path
        # may contain spaces, and this string becomes a shell command.
        import shlex
        extra = "".join(f" --writable {shlex.quote(str(w))}"
                        for w in (writable or []) if w)
        # `writable=` as well as the flags. They are TWO channels, not one: the
        # flags bound the sandbox, and `writable=` is what `ensure_governance_hook`
        # turns into `PWM_WRITABLE` for the hook that ASKS. This branch built the
        # flags and then omitted the argument, so the sandbox knew the declared
        # path and the hook did not — and a task standing in its own declared
        # working directory, granted and released to A1, had every write gated
        # by the boundary that had never heard of it.
        #
        # `claude_driver` already states the rule: the declared paths go to the
        # hook "so the hook and the sandbox draw the same boundary." Two
        # boundaries that disagree are one boundary and one blind spot.
        self.engine = spec
        # An unattended session has nobody to answer an approval prompt, and
        # `ai4science chat` gates every Edit/Write/Bash behind one. A GOVERNED
        # session therefore auto-approves and lets the hook be the boundary:
        # `ensure_governance_hook` is wired before launch and carries the same
        # declared paths, so the control is the ceiling rather than a prompt no
        # one can answer. An UNGOVERNED session keeps the prompt, because there
        # it is the only control there is.
        approve = " --yes" if govern else ""
        return sessions.start_session(
            name, cwd, govern=govern, ceiling=ceiling, writable=writable,
            claude_bin=f"ai4science chat --mode {spec}{extra}{approve}")

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
# UNION of both lines: main added `opencode`/`general-purpose`, the rename
# line added `ai4sci`. Dropping either silently makes that spec undrivable,
# and "undrivable" surfaces as a session that opens and never answers.
DRIVABLE_SPECS = {"claude-code", "codex", "opencode", "general-purpose",
                  "ai4sci", "unified-LLM"}
#: `unified-LLM` has been in this set three times. Twice it was taken out; the
#: third time it stayed, and the difference is what the entry means.
#:
#: **2026-08-07, first attempt — reverted the same day.** The evidence was one
#: screen capture in which the loop's matchers recognised the folder-trust gate.
#: A driven run then showed that is not the same thing: the ai4science TUI
#: leaves an answered gate's options in the transcript where Claude Code redraws
#: and they vanish, so the loop kept seeing a gate SHAPE after the gate was
#: answered, and once the identifying text scrolled away there was no rule to
#: match. Nine abstentions in one supervise run, five in the next.
#:
#: The comment then set the bar in two parts: **an answered gate must stop
#: looking like a pending one, AND a full run must be driven to a verdict.**
#:
#: **2026-08-07, third attempt — both parts met, and this is the evidence.**
#:
#:   * `operator._already_answered` distinguishes an answered gate from a
#:     pending one, by the echo line the TUI leaves after it;
#:   * task `tsk_d07da8e72e` on grace ran cold start → trust gate answered →
#:     brief delivered → plan-write gate answered → plan collected →
#:     awaiting-grant → released → `answered — a write the A2 ceiling now
#:     allows, asked before the task was released` → **`verified — the goal is
#:     met`**, with ZERO abstentions. The file it was asked for exists, 20
#:     bytes, first line exactly right.
#:
#: Five defects had to be fixed to get there, and every one of them was a
#: parity gap found by driving rather than by a test: a gate whose text the
#: terminal had wrapped, a multi-line brief submitted one line per prompt, a
#: plan path wrapped mid-word, a declared workdir never passed as writable, the
#: governance hook never told the declared paths, and a gate raised at A0 left
#: pending after the ceiling rose.
#:
#: The mistake worth not repeating is still the original one: **a matcher
#: succeeding on one captured screen is not the loop driving a session.**

#: Harness agent ID → openclaw agent ID for the three session agents that use
#: the two-layer architecture (openclaw gateway tmux pane + ACP control).
#: sarsi-worker in the harness maps to sarsi-claude in openclaw because the
#: harness uses the registry name while openclaw uses a separate namespace.
OPENCLAW_ACP_IDS: Dict[str, str] = {
    "sarsi-worker": "sarsi-claude",
    "sarsi-ai4sci": "sarsi-ai4sci",
    "sarsi-open":   "sarsi-open",
}


def executor_id_for(task: Any) -> str:
    """Which EXECUTOR runs this task — read off its BACKEND.

    SPEC-ai4science §8: *"sarsi-worker **guides** two engines: **sarsi-claude**
    to run Claude Code, and **sarsi-ai4sci** to run ai4sci"*, and [A1]:
    *"`/sarsi-ai4sci` and `/sarsi-claude` are **not** entry points — they are
    EXECUTORS, not listed and not entered."*

    So the engine is a property of the TASK, chosen per task, not a fixed
    property of the worker. `OPENCLAW_ACP_IDS` keys on the AGENT and maps
    `sarsi-worker -> sarsi-claude`, which pins the brain to one engine: a task
    whose backend is `sarsi-ai4sci` would then be handed to Claude Code, the
    record would name an executor the owner never chose, and the wrong engine
    would do the work. `backends._ACP_AGENTS` keys on the backend and is the
    source of truth; the agent map is the fallback for agents with no backend.
    """
    from ai4science.harness.agents.sarsi import backends as _bk
    name = (getattr(task, "backend", "") or "").strip()
    if name:
        try:
            return _bk.acp_agent_for(_bk.resolve(name))
        except Exception:
            pass
    return OPENCLAW_ACP_IDS.get(getattr(task, "agent_id", "") or "") or ""


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
        memory.record(config, agent, "clash",
                      f"assign on a task that already has a session",
                      f"task {task.id}: session "
                      f"{task.session.get('name', '?')} was already running — "
                      f"exactly-once violated.",
                      task_id=task.id)
        return task

    # Readiness gate — sync self model and check for gaps before spawning.
    # A stale authority or missing plan is logged as a refusal lesson so the
    # pattern is visible in MEMORY.md. Soft check for now: gaps are recorded
    # but do not block (M3 adds hard blocking once prediction records exist).
    try:
        from ai4science.harness.agents.sarsi import selfmodel as _sm
        _sm.sync(config, agent)
        # The operation-specific gate (§7.3), not the global health check. It
        # had no production caller at all — the live path asked one question
        # for every operation, which either blocks work that needed none of the
        # missing state or waves through work that needed all of it. `gate()`
        # asks what THIS operation declared it requires, refreshes what it can
        # a bounded number of times, and never turns retry exhaustion into a
        # value.
        got = _sm.gate(config, agent, "assign_executor", task=task)
        ready, gaps = got.ready, got.gaps
        for gap in gaps:
            memory.record(config, agent, "refusal",
                          f"readiness gap before assign: {gap[:120]}",
                          f"task {task.id}: {gap}", task_id=task.id)
        if got.exhausted:
            memory.record(config, agent, "refusal",
                          f"unmeasured after {_sm.DEFAULT_ATTEMPTS} attempts: "
                          f"{', '.join(got.exhausted)}",
                          f"task {task.id}: the declared observation path did "
                          f"not produce a value, and none was guessed")
    except Exception:
        pass

    # Register a pre-action forecast via forecast.py before spawning.
    # forecast.record() raises TooLate if the task already has a verdict, which
    # enforces the pre-action invariant without any additional guard here.
    # M3.2: calibration affects the forecast probability — if overconfident
    # (bias < -0.10 with at least 2 scored forecasts), use 0.5 instead of 0.7.
    # This is a bounded policy: it changes the recorded estimate but never
    # bypasses authority or required deterministic verification.
    try:
        from ai4science.harness.agents.sarsi import forecast as _fc
        index = tsk.earliest_incomplete(task)
        phase_str = f"phase {index + 1}" if index is not None else "final verification"
        p_forecast = 0.7
        sup = _fc.supervision(config, agent)
        if sup.level == "tighter":
            # The estimate moves, and so does the BEHAVIOUR: `require_
            # deterministic` is read in `_verify_phase`, where it stops a
            # model's opinion closing a phase no deterministic check could
            # judge. A calibration number that changed only another number
            # would be telemetry wearing a policy's name. [§M3.2]
            p_forecast = 0.5
            memory.record(config, agent, "refusal",
                          f"supervision tightened: {sup.why[:120]}",
                          f"task {task.id}: {sup.as_record()}",
                          task_id=task.id)
        # A forecast already on the task is somebody's estimate, and this one is
        # a CONSTANT. Overwriting it made the calibration record score 0.7 (or
        # 0.5) forever, so "overconfident" meant only that the default sits
        # above the observed pass rate — a property of the default, not of
        # anyone's judgement. §11.7 asks that scoring be immutable; it was
        # immutable after the verdict, via `TooLate`, and freely rewritten
        # right up to it.
        #
        # Registering only when none exists keeps §11.7's "pre-action forecast
        # is recorded in the live path" — a task assigned with no estimate
        # still gets one — while letting a considered estimate survive the
        # assignment that acts on it. The tightening path still fires: the
        # `refusal` episode above is written either way, and
        # `require_deterministic` is read from `supervision()` in
        # `_verify_phase` rather than from this number, so the BEHAVIOUR the
        # policy buys does not depend on which estimate is stored.
        if (task.forecast or {}).get("p") is None:
            _fc.record(config, agent, task, p_forecast,
                       why=f"sarsi-claude assigned for {phase_str} of {task.id}; "
                       f"p={p_forecast:.1f} "
                       + ("(conservative — overconfidence detected)" if p_forecast < 0.7 else "(default)"))
    except _fc.TooLate:
        # M3.1: "registration must occur before ses.assign()". The comment
        # above claimed this raise enforced the invariant while the blanket
        # except below swallowed it — so a session could be spawned on an
        # already-judged task with no forecast and no trace. It propagates.
        raise
    except Exception:
        pass

    # Which engine runs this task. The BACKEND is the task's — one worker runs
    # many tasks, and which engine ran a given one is a fact about that task.
    # A blank backend is an old record, and reads as the default rather than
    # as an error.
    from ai4science.harness.agents.sarsi import backends as _bk
    # The BACKEND says which engine; the AGENT says which ai4science agent that
    # engine runs. Reading only the backend made every worker start on
    # `unified-LLM` — the sarsi-pwm default — and the roster's own specs became
    # dead configuration, so `social` would have run the generalist under the
    # social agent's name. That is exactly what `test_it_never_substitutes_a_
    # generalist` forbids.
    #
    # `sarsi-claude` is the one backend that really does decide, because it
    # launches a vendor binary and no ai4science spec applies to it.
    _backend = _bk.resolve(getattr(task, "backend", ""))
    _engine = _bk.spec_for(_backend)
    if _backend == "sarsi-claude":
        run_spec = _engine
    else:
        # ...and `sarsi-pwm` means "NOT the vendor binary", so an agent whose
        # spec is `claude-code` takes the ai4science default instead. Honouring
        # it literally would make sarsi-pwm launch `claude`, which is the exact
        # thing choosing sarsi-pwm says you do not want — and it would put the
        # vendor-CLI requirement back into the backend that exists to remove it.
        _own = (getattr(agent, "spec", "") or "").strip()
        run_spec = _engine if _own in ("", "claude-code") else _own

    # The spec has to be here. Substituting a generalist would run the wrong
    # agent under the right label, which is worse than not starting at all.
    available = (installed or installed_specs)()
    if available and run_spec not in available:
        raise SpecUnavailable(
            f"{task.id} runs on the {run_spec!r} agent, which is not "
            f"installed here. Installed: {', '.join(sorted(available))}")

    # VLT for the secrets the DIRECTIVE declared. It has to be here rather than
    # at release: a secret reaches the session through the environment its tmux
    # process is created with, and a value decided after that process exists
    # cannot be injected into it. A secret the PLAN later discovers is handled
    # at `release`, honestly, by refusing rather than pretending.
    secrets = _unlock(config, agent, task, vault_prompt)

    # Three agents share a two-layer transport: the openclaw gateway manages
    # the tool session in a tmux pane (human visibility) while the harness
    # speaks ACP JSON-RPC to the gateway via `openclaw acp --session ID`
    # (programmatic control). See OPENCLAW_ACP_IDS for the harness→openclaw
    # ID mapping (they differ for sarsi-worker / sarsi-claude).
    #
    # Agents not in OPENCLAW_ACP_IDS (social, funding, jobs, etc.) run in a
    # regular tmux session via MachineRuntime and are attended by the owner.
    if runtime is None:
        openclaw_id = executor_id_for(task) or None
        if openclaw_id is not None:
            from ai4science.harness.agents.sarsi.acp import openclaw_acp_runtime
            runtime = openclaw_acp_runtime(openclaw_id)
        else:
            runtime = MachineRuntime()
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
    # INCLUDING the folder the session runs in. It used to be excluded, on the
    # assumption that a session's own cwd is writable by construction — true of
    # Claude Code's sandbox, false of PWM Code, where `--writable` is the only
    # declaration the governance hook reads (`_declared_writable` reads
    # `PWM_WRITABLE` and nothing else).
    #
    # Live, that assumption cost a whole run: the session stood in
    # `/home/grace/p3test`, the plan said write `DONE.md` there, the owner
    # granted exactly that, and every write was gated for ever. `release`
    # cannot repair it — `--writable` is fixed at launch and the hook reads an
    # environment that is already running.
    #
    # This widens nothing. It is the directory the owner typed into
    # `--workdir`, already an evidence root and already a blast-radius path.
    # Only a DECLARED directory is added. With none declared the workdir IS the
    # task folder, and passing it would turn "nothing was declared" into a flag
    # — `test_a_task_with_no_declared_directory_passes_none` is right that those
    # are different permissions.
    _declared = bool((task.work_root or "").strip())
    writable = [str(p) for p in tsk.evidence_roots(agent, task)
                if _declared or str(p) != str(workdir)]
    writable += [str(p) for p in (task.may_touch or [])]
    started = runtime.start(name, str(workdir), govern=True, ceiling=ceiling,
                            env=secrets, spec=run_spec,
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
                    # which transport owns this session: the routing helpers
                    # below read this to decide ACP round-trips vs tmux keystrokes.
                    # `openclaw_id` lets _rt() recover the right cached AcpRuntime.
                    "transport": "acp" if getattr(runtime, "acp", False) else "tmux",
                    "acp_spec": agent.spec,
                    # the executor the TASK chose, not one pinned to the agent
                    "openclaw_id": executor_id_for(task) or None,
                    "planner": agent.model,
                    }
    # The DURABLE HANDLE. An ACP session id is recorded so the gateway can still
    # be asked about this session after the process that made it has gone.
    # Copied only when present, so the tmux path's record is unchanged.
    # (Ported from the rename line; taking main's `assign` wholesale dropped it,
    # and without it a spawn's verdict cannot be recovered later at all.)
    for _k in ("runtime", "acp_session_id", "agent_id"):
        if (started or {}).get(_k) is not None:
            task.session[_k] = started[_k]
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


PROTECTED_VERIFIER_MODULES = ("verify", "verifier", "checkpoint")


def verifier_hashes() -> Dict[str, str]:
    """Current sha256 of each protected verifier module. [§M4.2]"""
    import hashlib
    import importlib
    from pathlib import Path as _Path

    out: Dict[str, str] = {}
    for mod_name in PROTECTED_VERIFIER_MODULES:
        try:
            mod = importlib.import_module(
                f"ai4science.harness.agents.sarsi.{mod_name}")
            out[mod_name] = hashlib.sha256(
                _Path(mod.__file__).read_bytes()).hexdigest()
        except Exception as exc:                       # pragma: no cover
            out[mod_name] = f"unreadable: {exc}"
    return out


def verifier_fingerprint() -> str:
    """One short id for the whole verifier, pinned into every verdict.

    §M4.2 asks for the verifier version/hash in the run evidence, and it was
    absent: a verdict recorded `state/why/engine/independent` and nothing that
    said WHICH verifier produced it. A stored verdict nobody can attribute to a
    version cannot be re-checked after the verifier changes.
    """
    import hashlib
    joined = ";".join(f"{k}={v}" for k, v in sorted(verifier_hashes().items()))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _check_verifier_integrity() -> tuple:
    """M4.2 — has anything rewritten the verifier since this process started?

    The baseline is taken at **import** (see `_VERIFIER_BASELINE` below), not
    on first call. It used to be populated lazily inside this function, whose
    only caller is `_verify_phase` — which runs *after* the executor session
    has already worked. So on a per-invocation CLI, which is the normal case,
    the first call had nothing to compare against and a `verify.py` already
    replaced with `def check(...): return PASS` was reported clean. Measured:
    a wholesale replacement went undetected, and the tampered module then
    passed every criterion.

    Taking it at import is not a complete answer either — a tamper that
    predates the process is invisible to any in-process hash — which is why
    the policy gate now refuses writes to these paths outright, and why the
    fingerprint travels in the verdict so a stored judgment can be attributed.
    """
    for mod_name, current_hash in verifier_hashes().items():
        try:
            baseline = _VERIFIER_BASELINE.get(mod_name)
            if baseline is None:
                # Should not happen: the baseline is taken at import. If it is
                # somehow absent, say so rather than adopting whatever is there
                # now as the truth — that is exactly the hole this had.
                return (False,
                        f"no import-time baseline for {mod_name}.py; this "
                        f"process cannot vouch for the verifier")
            if current_hash != baseline:
                return (False,
                        f"{mod_name}.py was modified during the executor session "
                        f"(baseline {baseline[:12]}… → current {current_hash[:12]}…); "
                        "this phase is rejected — no executor may touch verifier code")
        except Exception as exc:
            return (False, f"could not hash {mod_name}: {exc}")
    return (True, "")


#: Baseline hashes of the protected verifier modules, taken at IMPORT — before
#: any executor session can have run in this process. Populated lazily on first
#: call, it was always taken after the work it was meant to vouch for.
_VERIFIER_BASELINE: Dict[str, str] = {}


def _prime_verifier_baseline() -> None:
    if not _VERIFIER_BASELINE:
        _VERIFIER_BASELINE.update(verifier_hashes())


_prime_verifier_baseline()


def _step_is_spent(config: Config, agent: Agent, task: tsk.Task) -> bool:
    """Has this session used up the phases it was allowed to take on?

    `max_delegated_phases` came out of `forecast.supervision()` and nothing
    ever read it, so half of §M3.2's bounded policy was telemetry: calibration
    could tighten VERIFICATION and never the size of the step, which is the
    lever the section names first.
    """
    try:
        from ai4science.harness.agents.sarsi import forecast as _fc
        bound = _fc.supervision(config, agent).max_delegated_phases
    except Exception:
        return False
    if not bound:
        return False          # unbounded: the standing arrangement
    allowed = max(1, int(bound))
    if tsk.earliest_incomplete(task) is None:
        return False                       # finished; release happens anyway
    done = sum(1 for i in range(len(task.criteria or []))
               if tsk.phase_passed(task, i))
    return (done - int(getattr(task, "phases_at_assign", 0) or 0)) >= allowed


def _record_success(config: Config, agent: Agent, task: tsk.Task,
                    verdict: Dict[str, Any], *, now) -> None:
    """A verified pass, as an episode the consolidator can cluster. [§M5.1]

    Deliberately narrow: `high-value verified success if configured` in the
    spec, and what makes it high-value here is that a real verifier judged it.
    A model's opinion on a judgmental criterion produces an episode too, but
    one that says so — `deterministic` travels with it, so a procedure is
    never proposed from a workflow only a model ever blessed.
    """
    try:
        from ai4science.harness.agents.sarsi import memory as _mem
        phases = len(task.criteria or [])
        _mem.record_episode(
            config, agent, "success",
            f"verified: {(task.goal or '')[:150]}",
            f"{phases} phase(s) passed; engine={verdict.get('engine', '?')}; "
            f"deterministic={verdict.get('deterministic')}",
            task_id=task.id, outcome="pass",
            tags=["success", "workflow",
                  "deterministic" if verdict.get("deterministic") else "judged"],
            criteria=list(task.criteria or []),
            now=now)
    except Exception:
        pass


def check_expectations(config: Config, agent: Agent, *, now=time.time) -> list:
    """Tasks that were forecast, given a deadline, and blew through it. [§M5.1]

    "Timeout after a registered expectation" is the one hard trigger with no
    machinery behind it at all — nothing in the tree measured a registered
    expectation against the clock. A forecast carries `at`; a task carries
    `max_minutes`. That is a deadline, and passing it without a verdict is a
    machine-observable fact about a prediction that did not come true in time.

    Returns the episodes written, so a caller can report how many fired.
    """
    from ai4science.harness.agents.sarsi import memory as _mem
    fired = []
    try:
        rows = list(tsk.all_of(config, agent))
    except Exception:
        return fired
    for t in rows:
        fc_row = t.forecast or {}
        started = fc_row.get("at")
        limit = getattr(t, "max_minutes", None)
        if not started or not limit or (t.verdict or {}).get("state"):
            continue
        overdue = (float(now()) - float(started)) / 60.0 - float(limit)
        if overdue <= 0:
            continue
        if any(e.get("task_id") == t.id and e.get("trigger") == "expectation_timeout"
               for e in ledger.read(config, "episodes")):
            continue          # one episode per expectation, not one per sweep
        try:
            fired.append(_mem.record_episode(
                config, agent, "expectation_timeout",
                # The ninth writer, found by the M5.5 trigger-coverage
                # experiment after eight were fixed on 2026-08-24. The title is
                # what `consolidate._fingerprint` clusters on, so a task id at
                # the front makes every timeout its own group of one — and a
                # worker that keeps blowing deadlines on one KIND of task is
                # exactly the repeated pattern the offline pass exists to find.
                f"passed its deadline with no verdict: {(t.goal or '')[:110]}",
                f"task {t.id}: forecast p={fc_row.get('p')} registered "
                f"{overdue + float(limit):.1f} "
                f"minutes ago; limit was {limit} minutes and nothing has judged it",
                task_id=t.id, outcome="fail", tags=["timeout", "forecast"],
                now=now))
        except Exception:
            continue
    return fired


def _note_goal_drift(agent: Agent, task: tsk.Task,
                     verdict: Dict[str, Any]) -> Dict[str, Any]:
    """Put a rewritten goal ON the verdict, where a reader will meet it.

    A verdict that says PASS about a criterion nobody disputes is still the
    wrong answer if the goal underneath it was replaced — and the check cannot
    see that, because the check judges the criterion it was given.
    """
    try:
        note = tsk.goal_drift(agent, task)
    except Exception:
        return verdict
    if note:
        verdict = dict(verdict)
        verdict["goal_drift"] = note
    return verdict


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
        *(_memory_block(config, agent) or []),
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

    # ACP sessions have no screen to read back: delivery is the round-trip
    # itself, so the marker/acting heuristics below do not apply. The brief is
    # sent as a prompt, and on failure the session is resumed and re-briefed at
    # its first unverified phase rather than retyped at a screen.
    if (task.session or {}).get("transport") == "acp":
        return _deliver_kickoff_acp(config, agent, task, pending, runtime=runtime,
                                    now=now)

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


def acp_status(task: tsk.Task, *, home=None) -> Optional[Dict[str, Any]]:
    """What the gateway recorded about this task's ACP session, or None.

    An ACP session has no tmux pane, so the supervision loop cannot read a
    screen to learn how it is doing — and reading one anyway is what made the
    `do → run → supervise` path stall silently: `TmuxPane.capture` correctly
    returns None for a pane that does not exist, `tick` coerced it to `""`, and
    every screen-based branch then reasoned about a blank terminal.

    What an ACP session does expose is openclaw's own session store, and the
    session record already carries the key: `openclaw_id`. Looked up BY KEY
    rather than by "started after this spawn" — `session_store_lookup`'s
    time-window match exists for `spawn`, which has no id yet, and it refuses
    when several sessions match. Here the id is known, so the answer is exact.

    None means **unknown**, never "ended": no store, no entry, or an unreadable
    one are all absence of evidence, which is the same rule the store's own
    lookup states and the one a stall detector must not get wrong.
    """
    import json as _json
    import os as _os
    from pathlib import Path as _Path

    sess = task.session or {}
    key = sess.get("openclaw_id")
    if not key or sess.get("transport") != "acp":
        return None
    root = _Path(home) if home is not None else _Path(_os.path.expanduser("~"))
    engine = str(sess.get("engine") or "claude")
    path = root / ".openclaw" / "agents" / engine / "sessions" / "sessions.json"
    try:
        data = _json.loads(path.read_text())
        entry = data.get(key) if isinstance(data, dict) else None
    except Exception:
        return None
    if not isinstance(entry, dict):
        return None
    return {"status": str(entry.get("status") or ""),
            "started_at": entry.get("startedAt"),
            "ended_at": entry.get("endedAt"),
            "session_key": key}


def acp_ended(status: Optional[Dict[str, Any]]) -> bool:
    """Has the gateway session finished? Unknown is not finished."""
    if not status:
        return False
    if status.get("ended_at"):
        return True
    return str(status.get("status") or "").lower() in (
        "ended", "closed", "completed", "finished", "failed", "error")


def runtime_for(task: tsk.Task, runtime: Optional[Any] = None) -> Any:
    """The runtime that owns this task's session, by transport.

    The public name, because two callers outside this module use it and always
    did: `chat._guided` steers a plain line into a live session, and
    `retry.hand_back` reopens one. The rename to `_rt` never reached either, so
    both raised `AttributeError` the moment their own `runtime` was None — and
    the web gateway passes no runtime at all. Nothing in the suite caught it
    because every test hands one in; a live conversation found it on the second
    turn after a task was filed.

    Argument order is the caller's: the task is the subject, and an injected
    runtime is the optional override.
    """
    return _rt(runtime, task)


def _rt(runtime: Optional[Any], task: tsk.Task) -> Any:
    """The runtime that owns this task's session, by transport."""
    sess = task.session or {}
    if sess.get("transport") == "acp":
        openclaw_id = sess.get("openclaw_id")
        if openclaw_id:
            from ai4science.harness.agents.sarsi.acp import openclaw_acp_runtime
            return openclaw_acp_runtime(openclaw_id)
        # Fallback for sessions started before openclaw_id was recorded.
        acp_spec = sess.get("acp_spec", "opencode")
        if acp_spec == "opencode":
            from ai4science.harness.agents.sarsi.acp import acp_runtime
            return acp_runtime()
        from ai4science.harness.agents.sarsi.acp import ai4sci_acp_runtime
        return ai4sci_acp_runtime(acp_spec)
    # No session yet -- so dispatch by the task's BACKEND instead. Without this
    # a FRESH task on an ACP backend falls through to MachineRuntime and runs on
    # tmux, which cannot tell a refusal from a crash from a success. The revert
    # would be silent: the task still runs, and only the transport changes.
    #
    # (Ported from the rename line's `runtime_for`, which dispatched on backend
    # alone; this keeps the session-based path above as the authority when a
    # session exists, because the driver is a fact about the SESSION.)
    if runtime is None:
        # No session yet, so the answer comes from the task's BACKEND. Ported
        # verbatim in spirit from the rename line's `runtime_for`: resolve the
        # backend, ask whether its driver is ACP, and only then spawn. Without
        # this a FRESH task on an ACP backend falls through to MachineRuntime
        # and silently runs on tmux, which cannot tell a refusal from a crash
        # from a success.
        #
        # The BACKEND runtime, not the transport one: the transport attaches to
        # a session the gateway already owns, and a fresh task has none.
        # PREFER THE TRANSPORT when this agent maps to an openclaw agent id.
        # The gateway then owns the session and keeps it in a TMUX PANE, so the
        # owner can attach and WATCH the work happen. The backend below spawns
        # a bare stdio subprocess instead: full programmatic control, and
        # nothing to look at. Visibility is the whole reason the spec puts the
        # tool session in a pane, so it is the default when it is available.
        # NOT keyed on the agent. `OPENCLAW_ACP_IDS` maps sarsi-worker ->
        # sarsi-claude, so using it here would run a task whose BACKEND is
        # sarsi-ai4sci on Claude instead -- the wrong engine. The openclaw id
        # must come from the task's own backend.
        from ai4science.harness.agents.sarsi import backends as _bk
        name = (getattr(task, "backend", "") or "").strip()
        if name:
            try:
                chosen = _bk.resolve(name)
                driver = _bk.driver_for(chosen)
            except Exception:
                chosen, driver = "", ""
            if driver == "acp":
                # The BACKEND, deliberately -- not the gateway transport.
                #
                # The transport (`openclaw acp --session ID`) was tried here
                # first, because §11/[A12] wants a tmux pane the owner can
                # attach to. It does NOT produce one on this build: openclaw's
                # dist contains no tmux session management at all (only banner
                # and theme files mention it), and a live run created no pane
                # and no gateway session record. So preferring it broke two
                # tests and bought nothing.
                #
                # Watching a task work is a real requirement and it is still
                # unmet; it needs a mechanism that actually creates the pane,
                # not a different ACP endpoint.
                from ai4science.harness.agents.sarsi import acp_backend as _ab
                return _ab.AcpRuntime(agent_id=_bk.acp_agent_for(chosen))
    return runtime or MachineRuntime()


def _memory_block(config: Config, agent: Agent) -> Optional[List[str]]:
    """The lesson index, spliced into a brief when there is one.

    A lesson written by a trigger is only useful if the next brief carries it:
    the trap the memory exists for is the one repeated in a fresh session.
    """
    try:
        text = memory.load_index(config, agent)
    except Exception:
        return None
    if not text:
        return None
    return ["", text]


def _deliver_kickoff_acp(config: Config, agent: Agent, task: tsk.Task,
                         pending: str, *, runtime: Optional[Any] = None,
                         now=time.time) -> tsk.Task:
    """Deliver the kickoff brief to an ACP session.

    ACP delivery is a round-trip: the brief is a prompt, and the response is
    the confirmation. No screen to read, no marker to find. On failure the
    session is resumed and re-briefed at its first unverified phase.
    """
    if task.kickoff_tries >= MAX_KICKOFF_TRIES:
        task.kickoff_undelivered = True
        return tsk._touch(agent, task, now)

    name = (task.session or {}).get("name", "")
    cwd = (task.session or {}).get("cwd", "")
    rt = _rt(runtime, task)

    out = rt.send(name, pending) or {}
    if out.get("ok", True):
        task.kickoff_pending = None
        task.acts_at_kickoff = None
        task.kickoff_unreachable = False
        task.kickoff_tries += 1
        return tsk._touch(agent, task, now)

    task.kickoff_unreachable = True
    memory.record(config, agent, "refusal",
                  f"kickoff undelivered: the session refused the brief",
                  f"task {task.id}, session {name!r}: the ACP session declined "
                  f"the kickoff prompt; a resume was attempted.",
                  task_id=task.id,
                  now=now)
    try:
        rt.resume(name, cwd)
    except Exception:
        pass
    brief = _acp_resume_brief(config, agent, task)
    out2 = rt.send(name, brief) or {}
    if out2.get("ok", True):
        task.kickoff_pending = None
        task.acts_at_kickoff = None
        task.kickoff_unreachable = False
        task.kickoff_tries += 1
        return tsk._touch(agent, task, now)
    memory.record(config, agent, "refusal",
                  f"kickoff undelivered: the session refused the resume brief",
                  f"task {task.id}, session {name!r}: the ACP session declined "
                  f"the resume brief after a resume attempt.",
                  task_id=task.id,
                  now=now)
    task.kickoff_tries += 1
    if task.kickoff_tries >= MAX_KICKOFF_TRIES:
        task.kickoff_undelivered = True
    return tsk._touch(agent, task, now)


def _acp_resume_brief(config: Config, agent: Agent, task: tsk.Task) -> str:
    """A resume brief: the goal, the first unverified phase, and its criterion.

    Not the original kickoff — that was for a fresh session. A resumed session
    already has the context; it needs to know WHERE to pick up.
    """
    lines = [f"Goal: {task.goal}", ""]
    lines += _memory_block(config, agent) or []
    # A resumed session is about to act on what it last saw. Show it what is
    # true on disk right now, so it re-observes before it edits.
    try:
        stale = memory.staleness(config, agent, task)
    except Exception:
        stale = ""
    if stale:
        lines += [stale, ""]
    plan = tsk.read_plan_or_none(config, agent, task)

    # The checkpoint decides where a restart picks up — this is W3's actual
    # requirement, and until now `checkpoint.resume_point()` had no caller at
    # all: the live path read `earliest_incomplete()` off the task store, which
    # resumes at the right phase but has no plan-hash guard behind it. So a
    # plan rewritten under a running task resumed by phase INDEX, into work
    # that number no longer refers to.
    try:
        from ai4science.harness.agents.sarsi import checkpoint as _ck
        point = _ck.resume_point(config, agent, task)
    except Exception:
        point = None
    if point is not None and not point.ok:
        lines += [
            "STOP — do not resume yet.",
            point.why,
            "",
            "The phase numbers in the checkpoint no longer refer to the same "
            "work. Ask the owner to rebase or replan before continuing; "
            "picking a phase by its index would be a guess about which work "
            "still counts.",
        ]
        return "\n".join(lines)

    index = point.phase if (point is not None and point.phase is not None) \
        else tsk.earliest_incomplete(task)
    if plan and index is not None and index < len(plan.phases):
        phase = plan.phases[index]
        lines.append(f"Resume at phase {index + 1}: {phase.title}")
        if phase.verified_when:
            lines.append(f"Verified when: {phase.verified_when}")
        if phase.body:
            lines.append(phase.body)
        lines.append("")
        lines.append("Continue from where it stands. Do not redo completed phases.")
    else:
        lines.append("Continue from where it stands. Do not redo completed phases.")
    return "\n".join(lines)


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
        _rt(runtime, task).send(
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
    # Still PLANNING means the session drafted a plan and nothing attached it to
    # the task record, so there is no declared permission to have granted and
    # nothing to release against. `tsk.start` returns such a task UNCHANGED, so
    # this printed "tsk_… — planning": the owner handed back the state they
    # already knew, with no hint of the missing step. Every other refusal on
    # this path names its route; this one printed a noun.
    if task.state == tsk.PLANNING:
        raise NotReady(
            f"{task.id} is still planning: its plan has not been collected from "
            f"the session yet, so nothing has been declared to grant. Collect "
            f"it first — sarsi supervise {agent.id} {task.id} — which attaches "
            f"the plan and then says what to grant")
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
    rt = _rt(runtime, task)
    try:
        rt.set_ceiling((task.session or {}).get("name", ""), raised)
    except Exception as e:
        # NOT swallowed. This used to `pass` and then record `raised` anyway,
        # so a failed raise left the session running at A0 with every reader
        # showing the new ceiling. Honoured or refused, never dropped — the
        # same rule the governance wiring and the pane check now follow.
        raise CouldNotRelease(
            f"the ceiling would not raise to {raised}: {type(e).__name__}: {e}"
            f" — {task.id} is not released, because a task recorded at a "
            f"ceiling its session does not have is worse than one not released")
    if task.session:
        task.session["ceiling"] = raised
        task = tsk._touch(agent, task, now)
    # This call IS the boundary between planning and work — it is what raises
    # the ceiling from A0. Marking it here is what lets the declared budget
    # cover the WORK: without the mark, a task that spent its steps planning
    # arrives at its goal with nothing left, which is what happened live.
    task.steps_before_work = _steps_so_far(task, acts)
    task.work_started_at = float(now())
    # The owner's own mark. `work_started_at` is also set where planning ends,
    # so it cannot answer "did somebody with authority act on this?".
    task.released_at = float(now())
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

    runtime = _rt(runtime, task)
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
    # §12: auto-export on archive — "finished task can be put into md file".
    if archive:
        try:
            from ai4science.harness.agents.sarsi import export as _exp
            _exp.write(config, agent, task)
        except Exception:
            pass
    return task


def release_session(config: Config, agent: Agent, task: tsk.Task, *,
                    runtime: Optional[Any] = None, now=time.time) -> tsk.Task:
    """Close a finished task's terminal, and change nothing else.

    Live, `attention` reported it straight after a PASS: *"its task is verified
    but session sarsi-worker-5b2f is still running, holding whatever it was
    granted"*. The board was right and nothing acted on it — a live session at
    the released ceiling, with write permission to the working directory, and no
    task left that needs any of it. Every one of those grants was justified by a
    piece of work that has finished. It also holds one of the worker's
    concurrency slots, so a fleet that verifies ten tasks and closes none of
    them cannot start an eleventh.

    **Not `stop`.** That sets the state to `off`, which would erase the one
    outcome worth keeping. This closes the terminal and leaves the verdict, the
    plan and the state exactly as they are.

    Best-effort, for the same reason `stop` is: a tmux that will not die must
    not cost the record of work that was actually verified.
    """
    if task.steering_paused:
        # Interact handed the wheel to the owner. A verdict is not a reason to
        # take their terminal out from under them mid-keystroke; they close it
        # when they are done with it.
        return task
    name = (task.session or {}).get("name")
    if not name:
        return task

    try:
        from ai4science.harness.agents.sarsi import handoff as _ho
        _ho.write(config, agent, task)
    except Exception:
        pass                          # the record matters more than the note

    try:
        _rt(runtime, task).stop(name)
    except AttributeError:
        # The operator hands `verify` a `_Sender(pane)`, which can only TYPE.
        # Swallowing this cleared the record and left the terminal running —
        # `attention` then reported a session no task claims, holding whatever
        # it was granted, which is the exact thing this function exists to
        # prevent. A runtime that cannot stop is the CALLER's mistake, not a
        # machine failure, so fall back to the real one. `ses.stop` has carried
        # this same fallback, for this same reason, since before I wrote this.
        try:
            MachineRuntime().stop(name)
        except Exception:
            pass
    except Exception:
        pass                          # it may already be gone; the task is done

    # Kept, not cleared: `spend` finds the transcript through this working
    # directory, and a total that fell when a task SUCCEEDED is the one thing a
    # spend figure must never do.
    past = list(task.past_sessions or [])
    past.append(dict(task.session or {}, ended_at=now()))
    task.past_sessions = past
    task.session = None

    # Refresh self model so the cached snapshot reflects executor completion.
    try:
        from ai4science.harness.agents.sarsi import selfmodel as _sm
        _sm.sync(config, agent)
    except Exception:
        pass

    return tsk._touch(agent, task, now)


def work_dir_for(agent: Agent, task: tsk.Task):
    """Where this task's artifacts actually land — the one answer.

    The declared `work_root` when there is one, the task folder otherwise. A
    deterministic criterion is checked against this directory, so a caller
    (or a test) that guesses a different one is asking about a different place
    than the verifier looks. Two answers to "where is the work" is one more
    than a check can tolerate.
    """
    from pathlib import Path as _Path
    declared = (getattr(task, "work_root", "") or "").strip()
    if declared:
        try:
            return _Path(declared).expanduser().resolve()
        except OSError:
            pass
    return tsk.dir_of(agent, task.id)


def _verify_phase(config: Config, agent: Agent, task: tsk.Task, *,
                  verifier: Callable[..., Dict[str, Any]], evidence: str,
                  engine: Optional[str], index: int, now,
                  runtime: Optional[Any] = None) -> tsk.Task:
    """Judge ONE phase against ONE criterion.

    Judging a phase against every criterion would make "phase 1 passed" mean
    "everything passed", and the phase number would be decoration on a
    task-level verdict.
    """
    criteria = list(task.criteria or [])
    if index < 0 or index >= len(criteria):
        raise IndexError(f"{task.id} has {len(criteria)} phase(s); there is no "
                         f"phase {index + 1}")

    # M4.2: runtime verifier protection — hash protected modules before and
    # after executor session; fail the phase if they were modified.
    _verifier_ok, _verifier_reason = _check_verifier_integrity()
    if not _verifier_ok:
        _violation_verdict: Dict[str, Any] = {
            "state": "FAIL",
            "why": f"verifier integrity violation: {_verifier_reason}",
            "engine": "integrity-check",
            "independent": True,
            "criteria": [criteria[index] if criteria else ""],
            "phase": index + 1,
        }
        from ai4science.harness.agents.sarsi import memory as _mem
        _mem.record(config, agent, "refusal",
                    "verifier integrity check failed",
                    _verifier_reason)
        task.verdict = _violation_verdict
        return task

    # M4: deterministic check first — no LLM call when the criterion can be
    # evaluated programmatically. The worker may run checks but never writes.
    #
    # The guard covers the CHECK and nothing after it. It used to wrap the
    # recording too, and that hid a real defect for as long as it existed: the
    # FAIL path ends in `guide()`, `guide()` raised `UnboundLocalError` on
    # every call, and the exception unwound a verdict that had already been
    # recorded — straight into the LLM verifier, which said PASS. A
    # deterministic FAIL was reachable, correct, and thrown away. Whether the
    # steer could be delivered has no bearing on what the check found.
    _det_result = None
    try:
        from ai4science.harness.agents.sarsi import verify as _det
        # `trusted` is the owner's agreement, not the worker's confidence. On
        # the automatic path the SESSION writes plan0.md and its `Verified
        # when:` lines become the criteria verbatim — so an unagreed command
        # criterion is the judged party choosing its judge's code. [§M4.2]
        _agreed = bool(getattr(task, "plan_owner_edited", False))
        _det_result = _det.check(criteria[index], work_dir_for(agent, task),
                                 trusted=_agreed)
    except Exception:
        _det_result = None      # the check itself errored — the LLM verifier judges
    if _det_result is not None and _det_result.get("state") in ("PASS", "FAIL"):
        verdict: Dict[str, Any] = {
            "state": _det_result["state"],
            "why": _det_result.get("why", ""),
            "engine": "deterministic",
            "independent": True,   # code check, not the executor's self-report
            "check": _det_result.get("check", ""),
            "criteria": [criteria[index]],
            "phase": index + 1,
            "verifier": verifier_fingerprint(),
            "criterion_kind": "deterministic",
            "deterministic": True,
        }
        # Still note any plan drift so the owner sees it.
        verdict = _note_drift(agent, task, verdict,
                              tsk.criteria_drift(agent, task))
        verdict = _note_goal_drift(agent, task, verdict)
        from ai4science.harness.agents.sarsi import verifier as vf
        task = tsk.record_phase(config, agent, task, index, verdict, now=now)
        task.verdict = verdict
        # The deterministic branch RETURNS below, so the checkpoint written at
        # the end of this function was never reached from here — a task whose
        # phases are all deterministically checkable (the shape M4 pushes
        # toward) produced no checkpoint at all, and a restart had nothing to
        # resume from.
        try:
            from ai4science.harness.agents.sarsi import checkpoint as _ck
            _ck.write(config, agent, task)
        except Exception:
            pass
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id,
                       "state": "verified" if vf.is_pass(verdict) else "failed",
                       "verdict": verdict, "evidence": [_det_result.get("why", "")[:500]]},
                      now=now)
        if tsk.earliest_incomplete(task) is None:
            done = len(criteria)
            task = tsk.finish(config, agent, task, verdict={
                "state": "PASS",
                "why": f"every phase passed deterministic check: {done} of {done}",
                "engine": "deterministic",
                "independent": True,
                "criteria": criteria}, now=now)
            task = release_session(config, agent, task, runtime=runtime, now=now)
        elif vf.is_pass(verdict) and _step_is_spent(config, agent, task):
            # §M3.2's other half, which was set and never read: a worker whose
            # calibration bought a SMALLER delegated step now gets one. The
            # session that has used its allowance is released, so the next
            # phase starts in a fresh one — which is also what §M4.3 asks for,
            # a fresh executor per bounded step.
            task = release_session(config, agent, task, runtime=runtime, now=now)
        elif not vf.is_pass(verdict):
            # FAIL — steer the session back. Best effort: there may be no
            # session, it may not be drivable, or the owner may have the
            # wheel. None of those unmake the verdict.
            reason = verdict.get("why", "deterministic check failed")
            try:
                guide(config, agent, task,
                      f"Phase {index + 1} failed the deterministic check: {reason}\n"
                      "Address this and report what you did.",
                      runtime=runtime)
            except Exception:
                pass
        return tsk._touch(agent, task, now)

    # Tightened supervision, bought by measured overconfidence: no deterministic
    # criterion could judge this phase, and a worker that promises more than it
    # delivers does not get to close one on a model's opinion. Left UNVERIFIED
    # and handed back — which costs throughput and is the point. [§M3.2]
    try:
        from ai4science.harness.agents.sarsi import forecast as _fc
        _sup = _fc.supervision(config, agent)
    except Exception:
        _sup = None
    if _sup is not None and _sup.require_deterministic:
        held: Dict[str, Any] = {
            "state": "UNVERIFIED",
            "why": (f"no deterministic criterion could judge phase {index + 1}, "
                    f"and supervision is tightened: {_sup.why}"),
            "engine": "supervision-policy",
            "independent": True,
            "criteria": [criteria[index]],
            "phase": index + 1,
            "supervision": _sup.as_record(),
        }
        task.verdict = held
        ledger.append(config, "reports",
                      {"agent": agent.id, "task": task.id, "state": "unverified",
                       "verdict": held, "evidence": [evidence[:500]]}, now=now)
        try:
            guide(config, agent, task,
                  f"Phase {index + 1} cannot be closed on judgement here: "
                  f"{_sup.why}. Give it a criterion a check can evaluate — a "
                  f"command's exit code, a file, a hash — and report the result.",
                  runtime=runtime)
        except Exception:
            # Nowhere to steer (no session, not drivable, owner has the wheel).
            # The HELD verdict still stands: whether the message could be
            # delivered has no bearing on whether the phase was judged.
            pass
        return tsk._touch(agent, task, now)

    verdict = dict(verifier(goal=task.goal, criteria=[criteria[index]],
                            evidence=evidence) or {})
    verdict["engine"] = engine or "unknown"
    ran_it = (task.session or {}).get("engine") or agent.model or ""
    verdict["independent"] = bool(engine and engine != ran_it)
    verdict = _note_drift(agent, task, verdict,
                          tsk.criteria_drift(agent, task))
    verdict = _note_goal_drift(agent, task, verdict)
    verdict["criteria"] = [criteria[index]]
    verdict["phase"] = index + 1
    verdict["verifier"] = verifier_fingerprint()
    # The downgrade is stated. Reaching here means no deterministic check could
    # settle this criterion, so the phase is closing on a model's opinion —
    # §M4.1 forbids that happening SILENTLY, and a verdict that does not say so
    # reads afterwards exactly like a checked one.
    verdict["criterion_kind"] = "judgmental"
    verdict["deterministic"] = False

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

    # Write checkpoint.json so a restarted worker knows the verified phases
    # without parsing the full task store. Atomic, hashed to the plan it
    # describes, and carrying the verdict evidence per phase — see
    # `checkpoint.py` for why each of those three is not optional.
    try:
        from ai4science.harness.agents.sarsi import checkpoint as _ck
        _ck.write(config, agent, task)
    except Exception:
        pass

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
        # The loop reaches `verified` THROUGH HERE, not through the whole-task
        # path — `supervise` judges the phase the work is on. Releasing only
        # there covered the way a task finishes when the owner runs `check` by
        # hand, and left every loop-driven task holding its terminal.
        task = release_session(config, agent, task, runtime=runtime, now=now)
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
    _rt(runtime, task).send(name, instruction)
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id,
                   "state": "guided-by-owner" if by_owner else "guided",
                   "evidence": [instruction[:200]]}, now=now)
    # And into the SHARED history. It used to go to the ledger alone, while the
    # worker's workspace reads the ownerlog — so the one thing the owner said by
    # hand was the one thing the worker could not see, and the composer could
    # write the next prompt straight against it. Two drivers, one session: what
    # either does has to be visible to the other.
    try:
        # NOT `as _rt`: this module already has a module-level `_rt()` that
        # resolves the runtime, and importing the router under the same name
        # makes `_rt(runtime, task)` above an unbound local for the whole
        # function. Every owner guide raised UnboundLocalError before the
        # keystroke was ever sent.
        from ai4science.harness.agents.sarsi import ownerlog as _ol, router as _router
        _ol.append(config, agent, instruction,
                   surface=getattr(_router, "CLI_CHANNEL", "cli"),
                   mode="guided" if by_owner else "worker-guided", now=now)
    except Exception:
        pass          # a history that cannot be written must not stop the steer
    return task


def took_the_wheel(config: Config, agent: Agent, task: tsk.Task, *,
                   now=time.time) -> tsk.Task:
    """The owner has started hand-driving this session — stamp it.

    Pausing the operator stops it COLLIDING with the owner; it does not stop it
    steering wrong afterwards. Relaying never touches the goal, so `set_at` does
    not move and the plan still looks fresh — and the next pass drives
    confidently through phases the owner has just overridden by hand.

    The plan is WITHHELD, not deleted: `plan_version` survives, because deleting
    it would lose what the owner agreed to.
    """
    task.interact_at = float(now())
    tsk._save(agent, task)
    return task


def plan_is_stale(task: tsk.Task) -> bool:
    """`plan_at < max(set_at, interact_at)` — the same protection a re-set goal
    already had, extended to being hand-driven.

    The no-plan guard is borrowed from the proven implementation
    (`singularity web/runtime_agent.py:plan_is_stale`), which returns False when
    there is no plan file at all. "Stale" means WRITTEN FOR AN EARLIER GOAL; a
    task that has not planned yet is not stale, it has nothing — and without the
    guard every reader asking "should I withhold the plan?" gets a yes about a
    plan that does not exist.
    """
    if not getattr(task, "plan_version", 0):
        return False
    drafted = float(getattr(task, "plan_at", 0) or 0)
    return drafted < max(float(getattr(task, "set_at", 0) or 0),
                         float(getattr(task, "interact_at", 0) or 0))


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

        # WHERE IT STANDS. The kickoff said what to do and never what the
        # session was allowed to do — at exactly the moment the ceiling had just
        # changed, because `release` is what sends this. A session that does not
        # know its ceiling bumps into gates instead of planning around them, and
        # the loop has to nurse it through each one.
        #
        # The letter alone answers nothing, so the permission is spelled out;
        # this is the same table `selfaware` renders for the worker, because two
        # descriptions of one ladder will disagree.
        #
        # Silent when no ceiling is recorded: an invented one is worse than
        # none, since the session would plan against it.
        _ceiling = str((task.session or {}).get("ceiling") or "")
        if _ceiling:
            from ai4science.harness.agents.sarsi import selfaware as _sa
            _permits = _sa.PERMITS.get(_ceiling)
            if _permits:
                lines.append(f"You are at ceiling {_ceiling}. You may "
                             f"{_permits}. Anything beyond that stops for the "
                             f"owner — ask rather than work around it.")

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


def _settle_deterministically(agent: Agent, task: tsk.Task,
                              criteria: List[str]):
    """Split criteria into {criterion: verdict} settled by code, and the rest.

    `trusted` is the OWNER's agreement, not the worker's confidence — the same
    rule `_verify_phase` applies, and for the same reason: on the automatic
    path the session writes `plan0.md`, so an unagreed command criterion would
    be the judged party choosing its judge's code. [§M4.2]
    """
    settled: Dict[str, Any] = {}
    rest: List[str] = []
    try:
        from ai4science.harness.agents.sarsi import verify as _det
    except Exception:
        return {}, list(criteria)
    trusted = bool(getattr(task, "plan_owner_edited", False))
    work = work_dir_for(agent, task)
    for c in criteria:
        try:
            r = _det.check(c, work, trusted=trusted)
        except Exception:
            r = None                # the check errored — the model judges it
        if r is not None and r.get("state") in ("PASS", "FAIL"):
            settled[c] = r
        else:
            rest.append(c)
    return settled, rest


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
    #   * the owner RELEASED the task (`released_at`, set by `release` and nowhere
    #     else) — they read the plan, granted each
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
    released = task.released_at is not None
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
                             runtime=runtime, now=now)

    criteria = list(task.criteria or [])

    # Deterministic first, here as in `_verify_phase`. §0.1 rule 6: if a pass
    # condition can be expressed as a test, a file check, a JSON predicate or
    # an exit code, do that rather than ask a model — and this path did not.
    # It handed EVERY criterion to the verifier, including ones `verify.check`
    # settles outright, which is the path `sarsi check <agent> <task>` takes
    # whenever no `--phase` is given: the owner's default. Measured
    # 2026-08-24: `verify.check` returned PASS on "manifest.json exists" while
    # the model verifier's FAIL was recorded as the task's verdict.
    settled, unsettled = _settle_deterministically(agent, task, criteria)

    failed_checks = [c for c, r in settled.items() if r["state"] == "FAIL"]

    if failed_checks or (settled and not unsettled):
        # Either code answered everything, or it FAILED something. A check that
        # failed is not up for review: a model PASS over it would be the judged
        # party's opinion beating the evidence, which is the one direction that
        # must never be possible.
        named = failed_checks or list(settled)
        verdict = {
            "state": "FAIL" if failed_checks else "PASS",
            "why": "; ".join(settled[c].get("why", "") for c in named)[:800],
            "engine": "deterministic",
            "independent": True,          # code check, not the executor's word
            "deterministic": True,
            "settled_by_check": list(settled),
        }
        if unsettled:
            # Say what was NOT asked, so a reader never mistakes an unfinished
            # judgement for a complete one. [§0.1 rule 7]
            verdict["not_judged"] = list(unsettled)
    else:
        verdict = dict(verifier(goal=task.goal, criteria=unsettled or criteria,
                                evidence=evidence) or {})
        if settled:
            verdict["settled_by_check"] = list(settled)

    verdict = _note_drift(agent, task, verdict, drifted)
    verdict = _note_goal_drift(agent, task, verdict)
    verdict["engine"] = verdict.get("engine") or engine or "unknown"
    # A different engine is the cheapest independence there is; when it is the
    # same one, say so rather than claiming an independence we do not have.
    # Compared against the engine that RAN the session: the live run recorded
    # `independent: true` for a claude-judged, claude-executed task because the
    # worker's planning model happened to be a different string.
    ran_it = (task.session or {}).get("engine") or agent.model or ""
    if not verdict.get("deterministic"):
        # A code check IS independent of whoever ran the session; only a model
        # verdict has to argue for it by being a different engine.
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
        # §M5.1's eighth trigger: a verified success is evidence too, and it
        # is the ONLY evidence a procedure can be built from. Nothing wrote it,
        # so `consolidate`'s success arm — and every skill candidate behind it
        # — was unreachable from the live path however often a workflow
        # actually worked. Only a VERIFIED pass counts; the executor saying so
        # is not the trigger.
        _record_success(config, agent, task, verdict, now=now)
        return release_session(config, agent, task, runtime=runtime, now=now)

    task.verdict = verdict
    task.state = tsk.RUNNING
    task = tsk._touch(agent, task, now)
    why = verdict.get("why") or "the verifier was not satisfied"
    # The TITLE is what `consolidate._fingerprint` clusters on — its first 40
    # characters. Leading with the task id, which is 14 characters and different
    # every time, meant two identical failures were two groups of one, and the
    # semantic arm of the consolidator could never reach `MIN_SUPPORT` from the
    # live path however often the same thing broke. The id belongs in the
    # episode's own `task_id` field, where it is traceable and does not decide
    # what looks like what. [§5.3, §11.9(b)]
    memory.record(config, agent, "refuted_prediction",
                  f"refuted: {task.goal[:120]}",
                  f"task {task.id}: the verifier said: {why[:800]}",
                  task_id=task.id, now=now)
    steered = False
    # Not at an interface this loop cannot read. `check` on an attended agent
    # was typing this paragraph at whatever screen happened to be showing —
    # the same hazard `guide` refuses, one command earlier and unnoticed. Quiet
    # here rather than raised: judging is not steering, and a verdict must not
    # be lost because it could not also be delivered. `steered` stays False,
    # which the ledger below already reports honestly.
    if task.session and drivable(agent.spec):
        try:
            _rt(runtime, task).send(
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
    #
    # The PAST one counts. A verified task closes its terminal, and "session X,
    # verdict PASS" is how the record says which run produced the result —
    # letting go of the terminal must not take that with it.
    name = ((task.session or {}).get("name")
            or ((task.past_sessions or [{}])[-1]).get("name") or "")
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
