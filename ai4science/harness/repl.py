"""Native-harness REPL for both --mode common and --mode research.

A self-contained input()-loop that builds an AgentSession from the harness
adapter factory, streams text to stdout, handles /exit and /model, and
meters usage via the ledger.  No claude_agent_sdk dependency.

This module is intentionally free of Typer / Rich so that it can be imported
and unit-tested without a TTY.

Integration: ai4science/commands/chat.py resolves --mode against the agent
registry and calls run_common_repl() with mode_label + the spec's system_prompt
(as a fallback). The active AgentSpec — resolved inside run_common_repl from
mode_label — drives the tool registry and grounding prompt for the session.
Slash commands: /help /clear /model /readonly /yes /default /cost /files /exit.
Session history is persisted per turn and reseeded via --continue / --resume.
"""
from __future__ import annotations

import os
import pathlib
import re
import secrets
import sys
from pathlib import Path
from typing import List, Optional

from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.harness.agents import registry as agent_registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for
from ai4science.harness.events import Message
from ai4science.harness.session import AgentSession
from ai4science.harness.pwm_gate import PwmGate, BASE_TOOLS
from ai4science.llm import routing, pricing


def _shortcwd(p) -> str:
    import os
    try:
        s = str(p); h = os.path.expanduser("~")
        return ("~" + s[len(h):]) if s.startswith(h) else s
    except Exception:
        return str(p)


#: Commands the loop answers itself, which never reach `_dispatch_slash` because
#: they need the live session. A resolver built only from the dispatcher would
#: call these unknown — the same defect wearing a helpful face.
_LOOP_COMMANDS = ("model", "agent", "mode", "cost", "files", "agents", "mcp",
                  "feedback", "login", "whoami",
                  "install-agent", "uninstall-agent")

_COMMAND_WORD = re.compile(r"^/([A-Za-z][A-Za-z0-9_-]*)(\s|$)")


def known_commands() -> set:
    """Every slash this REPL answers — the dispatcher's and the loop's."""
    names = set(_LOOP_COMMANDS)
    src = _source()
    for m in re.finditer(r"""cmd\s*==\s*["'](\w+)["']""", src):
        names.add(m.group(1))
    for m in re.finditer(r"""cmd\s+in\s+\(([^)]*)\)""", src):
        names.update(re.findall(r"""["'](\w+)["']""", m.group(1)))
    return names


#: Every Action kind the loop performs. Asserted against what `console.route`
#: can return, because an action the console produces and the loop does not
#: handle is a command that silently does nothing.
HANDLED_ACTIONS = {"answer", "say", "confirm", "create", "guide", "attach",
                   "enter", "leave", "noop", "task-verb"}


def _prompt_for(state: dict) -> str:
    from ai4science.harness import console as _c
    return _c.prompt_label(state.get("mode") or _c.Mode())


def _attach_tmux(session: str, *, task: str = "", agent: str = "", run=None) -> str:
    """Hand the terminal to tmux and take it back.

    `run` is injected so tests assert what was asked for without attaching
    anything. This is the one part of this piece that cannot be honestly
    unit-tested: prompt_toolkit must release the terminal, a child takes it,
    and the app is restored on return. If that goes wrong the failure mode is
    an unusable terminal, which is why `/interact --print` exists.

    The caller pauses the worker (`_pause_for_interact`) BEFORE calling this,
    the same way `sarsi/chat.py:_interact` does for the board — so by the
    time this prints "paused" it already is. `task`/`agent` are only used to
    name a REAL way back: this REPL has no `/resume` slash, so the closing
    line points at the CLI door that does (`sarsi ask <agent> "/resume …"`)
    rather than a command that would 404.
    """
    import os
    import subprocess
    # $TMUX stripped so the attach works when the REPL itself runs inside
    # tmux — without this, nesting is refused outright (exit 1) and the
    # owner never even reaches the session.
    _env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    caller = run or (lambda a: subprocess.call(a, env=_env))

    # ONE key back: Ctrl-z detaches, for the duration of this attach only.
    # The prefix chord (Ctrl-b d) still works standalone, but nested inside
    # another tmux the OUTER server eats the prefix — Ctrl-z is not a prefix,
    # so it reaches the inner server either way. Bound before the terminal is
    # handed over, unbound after it comes back: a root-table binding left
    # behind would turn Ctrl-z into detach for every session on this server.
    bound = False
    try:
        try:
            caller(["tmux", "bind-key", "-n", "C-z", "detach-client"])
            bound = True
        except Exception:
            pass                # no binding is a degraded attach, not a failed one
        if bound:
            print(f"entering {session} — press Ctrl-z to come back here",
                  flush=True)
        try:
            rc = caller(["tmux", "attach", "-t", session])
        except Exception as e:
            return (f"could not attach {session} — {type(e).__name__}: {e}\n"
                    f"  attach it yourself: tmux attach -t {session}")
        if rc:
            return (f"tmux would not attach {session} (exit {rc})\n"
                    f"  is it still running? ai4science sarsi tasks <agent>")
    finally:
        if bound:
            try:
                caller(["tmux", "unbind-key", "-n", "C-z"])
            except Exception:
                pass
    if agent and task:
        return (f"back from {session} (Ctrl-z came home). {task} is paused — "
                f"the worker will not steer it again until you resume it:\n"
                f"  ai4science sarsi ask {agent} \"/resume {task}\"")
    return f"back from {session} (Ctrl-z came home)."


def _console_deps(state: dict) -> dict:
    """The world, as callables `console.route` can index.

    Every one returns a value or a string — never raises. `route` reads these
    keys directly, and a KeyError or an exception here lands inside the REPL
    loop, which is the one place nothing may drop the session.
    """
    def _config():
        from ai4science.harness.agents.sarsi import registry as reg
        return reg.load()

    def _session_of(task_id: str) -> str:
        try:
            agent, t = _find_task(_config(), task_id)
            if t is None:
                return ""
            s = t.session if isinstance(t.session, dict) else None
            return (s or {}).get("name") or ""
        except Exception:
            return ""

    def _create(agent_id: str, goal: str, backend: str = "") -> str:
        try:
            from ai4science.harness.agents.sarsi import chat as _sc
            config = _config()
            agent = config.agents.get(agent_id)
            if agent is None:
                return f"{agent_id} is not on this machine"
            # _new() picks backend, starts state machine, and auto-starts session.
            result = _sc._new(config, agent, goal, "cli")
            # Extract task id from the first line of the result for the confirm display.
            first = (result or "").splitlines()[0] if result else ""
            import re as _re
            m = _re.search(r"tsk_\w+", first)
            return result if result else (m.group(0) if m else goal)
        except Exception as e:
            return f"could not create it — {e}"

    def _guide(task_id: str, text: str) -> str:
        try:
            from ai4science.harness.agents.sarsi import session as ses
            config = _config()
            agent, t = _find_task(config, task_id)
            if t is None:
                return f"{task_id} is not a task on this machine"
            ses.guide(config, agent, t, text, by_owner=True)
            return f"sent, ahead of the worker — {text[:80]}"
        except Exception as e:
            return f"could not steer it — {e}"

    def _suggest(text: str) -> str:
        try:
            from ai4science.harness.agents.sarsi import triage
            got = triage.suggest(_config(), text)
            if got.best is None:
                return ""          # a tie or nothing: a router that guesses is
                                   # worse than one that is quiet
            return (f"  ───\n  {got.best.agent_id} could take this as a task "
                    f"instead — /{got.best.agent_id} to enter it")
        except Exception:
            return ""

    def _find(task_id: str):
        try:
            return _find_task(_config(), task_id)
        except Exception:
            return (None, None)

    def _pause_for_interact(task_id: str) -> str:
        """Pause worker steering BEFORE the terminal is handed to tmux —
        mirrors `sarsi/chat.py:_interact`, the board's own way in, so
        `/interact` here is not a second, weaker implementation of the same
        promise. Returns the agent id (so the closing message can point at a
        real resume path) or "" if there was nothing to pause.
        """
        try:
            from ai4science.harness.agents.sarsi import task as tsk
            import time as _time
            config = _config()
            agent, t = _find_task(config, task_id)
            if t is None or not t.session:
                return ""
            t.steering_paused = True
            t.plan_stale = True          # the owner may abandon phases by hand
            t.criteria = []              # a stale plan's criteria are withheld
            # And the TIMESTAMP the design names. `plan_stale` is a flag someone
            # has to remember to clear; `interact_at` is a fact, and staleness
            # derives from it — `plan_at < max(set_at, interact_at)` — so a plan
            # drafted AFTER the owner drove is fresh again without anyone
            # resetting anything. The flag stays: it is what today's readers use.
            from ai4science.harness.agents.sarsi import session as _ses
            _ses.took_the_wheel(config, agent, t, now=_time.time)
            tsk._touch(agent, t, _time.time)
            return agent.id
        except Exception:
            return ""

    def _about_self(agent_id: str) -> str:
        """What this worker can truthfully say about itself, or "".

        Never raises: this text reaches the prompt the owner is standing in, and
        a raise there would drop the REPL.
        """
        try:
            from ai4science.harness.agents.sarsi import selfaware
            config = _config()
            agent = config.agents.get(agent_id)
            if agent is None:
                return ""
            return selfaware.describe(config, agent)
        except Exception:
            return ""

    def _task_status(task_id: str) -> str:
        """The task's record, for a question asked in guided mode — with the
        one fact the guided prompt otherwise hides: nothing was sent."""
        try:
            config = _config()
            agent, t = _find_task(config, task_id)
        except Exception as e:
            return f"could not read {task_id}: {e}"
        if t is None:
            return f"{task_id} is not a task on this machine — /task lists them"
        lines = [task_view(config, agent, t)]
        try:
            from ai4science.harness.agents.sarsi import task as tsk
            plan = tsk.read_plan(config, agent, t)
            if plan:
                lines.append("  plan:")
                lines.extend("    " + ln for ln in plan.render().splitlines())
            else:
                lines.append("  no plan yet — the session drafts one at A0")
        except Exception:
            pass
        for key in sorted((t.phase_verdicts or {}), key=str):
            v = (t.phase_verdicts or {}).get(key) or {}
            reason = str(v.get("reason", ""))[:120]
            lines.append(f"  phase {int(key) + 1 if str(key).isdigit() else key}"
                         f": {str(v.get('state', '?')).upper()}"
                         + (f" — {reason}" if reason else ""))
        lines.append(
            "  (answered from the task's record — nothing went to the "
            "session.\n"
            "   steer it: say it as an instruction · watch it: "
            "/interact --print\n"
            f"   full verdicts: ai4science sarsi why {agent.id} {t.id})")
        return "\n".join(lines)

    def _task_verb(verb: str, task_id: str, rest: str) -> str:
        """The owner's lifecycle acts, from the REPL — the same library calls
        the CLI verbs make, so the two doors cannot drift."""
        try:
            config = _config()
            agent, t = _find_task(config, task_id)
        except Exception as e:
            return f"could not read {task_id}: {e}"
        if t is None:
            return f"{task_id} is not a task on this machine — /task lists them"
        from ai4science.harness.agents.sarsi import (chat as sarsi_chat,
                                                     session as ses,
                                                     task as tsk)
        label = f"{t.name}---task" if t.name else t.id
        try:
            if verb == "stop":
                ses.stop(config, agent, t)
                return (f"{label} stopped — its slot is free. Pick it up "
                        f"again: ai4science sarsi run {agent.id} {t.id}")
            if verb == "archive":
                ses.stop(config, agent, t, archive=True)
                return f"{label} archived — off the board, and kept"
            if verb == "reopen":
                if t.state != tsk.ARCHIVED:
                    return f"{label} is not archived — it is {t.state}"
                tsk.reopen(config, agent, t)
                return f"{label} is back on the board, stopped"
            if verb == "goal":
                if not rest:
                    return "usage: /goal [task] <the new goal, one sentence>"
                return sarsi_chat.handle(config, agent,
                                         f"/goal {t.id} {rest}", surface="cli")
            if verb == "rename":
                if not rest:
                    return "usage: /rename [task] <new name>"
                tsk.rename(config, agent, t, rest)
                return f"{t.id} is now {t.name}---task"
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"could not {verb} {label}: {type(e).__name__}: {e}"
        return f"/{verb} is not an owner act this REPL knows"

    return {"resolve": resolve_name, "find_task": _find, "suggest": _suggest,
            "create": _create, "guide": _guide, "session_of": _session_of,
            "pause_for_interact": _pause_for_interact, "unknown": slash_answer,
            "about_self": _about_self, "task_status": _task_status,
            "task-verb": _task_verb}


def _source() -> str:
    try:
        return pathlib.Path(__file__).read_text()
    except OSError:                              # zipped install, frozen, …
        return ""


def looks_like_command(line: str) -> bool:
    """Is this an attempt at a slash, or a sentence that starts with a path?

    `/sarsi-worker` is an attempt. `/home/grace/x is missing` is a sentence, and
    refusing it would be worse than the bug this fixes — a user quoting a path
    should not have to escape anything. The separator is structure: a name is
    one word, a path has slashes or dots inside it.
    """
    m = _COMMAND_WORD.match(line or "")
    if not m:
        return False
    first = (line or "").split()[0]
    return "/" not in first[1:] and "." not in first[1:]


def _chat_specs() -> set:
    """Spec names, loading the registry if nothing has yet.

    `AGENT_REGISTRY` is populated by `reload()` at CLI start, so reading it cold
    — from a test, or before the first turn — gives an empty set and every name
    resolves to "unknown". Asking for it is what makes the answer true.
    """
    try:
        from ai4science.harness.agents import registry as ar
        if not ar.AGENT_REGISTRY:
            try:
                ar.reload()
            except Exception:
                pass
        return set(ar.AGENT_REGISTRY)
    except Exception:
        return set()


def _roster_agents() -> set:
    """Roster ids, from this machine's registry when it has one and from the
    shipped roster when it does not. A box that never ran `sarsi init` should
    still be able to explain what the name means.

    The hostname is included as an alias for sarsi-machine so that
    `/<hostname>` is recognised as a roster command [A21(b)]."""
    from ai4science.harness.agents.sarsi import registry as reg
    try:
        names = set(reg.load().agents)
    except Exception:
        try:
            names = {a["id"] for a in reg._ROSTER}
        except Exception:
            names = set()
    names.add(_machine_hostname())
    return names


def resolve_name(name: str):
    """What does `/name` refer to? -> (kind, detail).

    kind is one of: command, task, spec, roster, both, unknown.

    `both` exists because two agents are called `work` and they are different
    things: the chat spec ANSWERS in your session, the roster agent DELEGATES
    to a Claude Code session. Choosing between them silently is how the
    confusion started.
    """
    low = (name or "").strip().lower()
    if not low:
        return "unknown", ""
    if low in known_commands():
        return "command", low
    if low.startswith("tsk_"):
        return "task", low
    named = _task_by_name(low)
    if named:
        return "task", named
    spec = low in {s.lower() for s in _chat_specs()}
    roster = low in {a.lower() for a in _roster_agents()}
    if spec and roster:
        return "both", (
            f"{low} is BOTH: a chat spec (answers here, in this session) and a "
            f"sarsi roster agent (holds tasks and drives a Claude Code session)")
    if spec:
        return "spec", low
    if roster:
        return "roster", low
    return "unknown", low


def _task_by_name(low: str) -> str:
    """The task id wearing this name, or "". Names lose to everything that
    resolves earlier (commands, `tsk_` ids) — a name may not shadow either."""
    if not low or low.startswith("tsk_"):
        return ""
    try:
        from ai4science.harness.agents.sarsi import registry as reg
        config = reg.load()
        for _agent, t in all_tasks(config):
            if (t.name or "").lower() == low:
                return t.id
    except Exception:
        pass
    return ""


def slash_answer(line: str) -> str:
    """What to print for a slash the command chain did not handle.

    A slash addresses the HARNESS rather than the model. Forwarding one silently
    turns a typo into a paid turn whose output reads like an answer to a
    question nobody asked — and, worse, `/sarsi-worker` LOOKED like it had
    switched agent when it had done nothing of the kind.
    """
    import difflib
    m = _COMMAND_WORD.match(line or "")
    if not m:
        return ""
    name = m.group(1)
    kind, detail = resolve_name(name)
    if kind == "both":
        return (f"{detail}.\n"
                f"  the one that answers here: /agent {name}\n"
                f"  the one that delegates:   /{name} do <goal>  "
                f"(or: ai4science sarsi do {name} \"<goal>\")")
    if kind == "roster":
        return (f"{name} is a sarsi roster agent — it holds tasks and drives "
                f"sessions rather than answering here.\n"
                f"  give it work: /{name} do <goal>\n"
                f"  see its board: /{name} tasks")
    if kind == "task":
        return (f"{name} is a task id. Open it with /tasks, or work it from the "
                f"CLI: ai4science sarsi run <agent> {name}")
    msg = f"/{name} is not a command, and it was NOT sent to the model."
    close = difflib.get_close_matches(name.lower(), sorted(known_commands()),
                                      n=2, cutoff=0.6)
    if close:
        return msg + " Did you mean " + " or ".join("/" + c for c in close) + "?"
    return msg + " /help lists them."


def _dispatch_slash(line: str, state: dict) -> tuple[bool, str]:
    """Handle simple slash commands by mutating `state`. Returns (handled, message).

    /model, /cost, /files are handled in the loop (they need the live session).
    """
    cmd, _, _arg = line[1:].partition(" ")
    cmd = cmd.lower().strip()
    if cmd in ("exit", "quit", "q"):
        state["exit"] = True
        return True, "bye"
    if cmd in ("help", "?"):
        return True, ("slash commands: /help /clear /model <backend> [id] "
                      "/agent [name|specific <q>] /do <goal> /tasks /login "
                      "/whoami /feedback <text> /readonly /yes /default "
                      "/cost /files /subagents /exit\n"
                      "  agents: /install-agent [name] (add to /agent picker) "
                      "/uninstall-agent [name] (remove from picker)\n"
                      "  tasks: /task (all boards) /<task-name> or /tsk_… "
                      "(open, guided) /interact (its terminal — Ctrl-z back) "
                      "/rename /goal /stop /archive /reopen [task] — owner "
                      "acts on the task named, or the one you stand in\n"
                      "  /do hands the goal to this agent's sarsi worker "
                      "(task + plan + sarsi-claude) instead of answering here\n"
                      "  /subagents lists the nested delegation types the "
                      "task tool can hand a focused sub-task to")
    if cmd == "readonly":
        state["read_only"] = True
        return True, "read-only: ON (mutating tools blocked)"
    if cmd == "yes":
        state["auto_yes"] = True
        return True, "auto-yes: ON (tools auto-approved)"
    if cmd == "default":
        state["read_only"] = False
        state["auto_yes"] = False
        return True, "default mode (per-edit confirmation)"
    if cmd == "clear":
        state["clear"] = True
        return True, "conversation cleared"
    if cmd in ("agent", "agents", "mode"):
        # These need the live session (TUI picker, session rebuild) and are
        # answered inline in the loop — but a dispatcher that calls a KNOWN
        # command unhandled is the same defect this module exists to remove,
        # so it is at least recognized here.
        return True, ""
    if cmd == "subagents":
        # `/agents` used to print this — the nested `task`-tool delegation
        # types (unrelated to the chat-agent switcher, which is what /agents
        # became). Moved here, wording unchanged, so making /agents the
        # switcher didn't delete a user-reachable listing to free up a name.
        from ai4science.harness.subagents import SUBAGENTS
        lines = ["sub-agents:"] + [f"  {n}: {p['description']}"
                                    for n, p in sorted(SUBAGENTS.items())]
        return True, "\n".join(lines)
    if cmd in ("do", "tasks"):
        return True, _sarsi_bridge(cmd, _arg.strip(), _bridge_target(state))

    if cmd == "install-agent":
        return True, _install_agent_cmd(_arg.strip())

    if cmd == "uninstall-agent":
        return True, _uninstall_agent_cmd(_arg.strip())

    # `/<roster-agent> do <goal>` and `/<roster-agent> tasks`. `/do` reaches the
    # sarsi worker whose id matches the CHAT AGENT's name, so a roster agent
    # with no chat spec — `sarsi-worker`, the general worker — could not be
    # addressed from the REPL at all. Naming it directly is the way in.
    if cmd == "task" or cmd.startswith("tsk_"):
        return True, _task_slash(cmd, _arg.strip())

    kind, _detail = resolve_name(cmd)
    if kind in ("roster", "both"):
        verb, _, rest = _arg.strip().partition(" ")
        verb = verb.lower().strip()
        if verb in ("do", "tasks"):
            return True, _sarsi_bridge(verb, rest.strip(), cmd)
        if not verb:
            return True, slash_answer(line)
    return False, ""


def all_tasks(config):
    """Every task on the machine, with the agent that holds it.

    `/tasks` shows one agent's board — the chat agent's. An owner handed a task
    name has no reason to know which agent owns it, so `/task` looks everywhere.
    """
    from ai4science.harness.agents.sarsi import task as tsk
    out = []
    for agent in config.agents.values():
        try:
            for t in tsk.all_of(config, agent):
                out.append((agent, t))
        except Exception:
            continue
    return out


def task_view(config, agent, task) -> str:
    """One task, and the two ways into it.

    **Guided** steers from outside: the owner's word goes in ahead of the
    worker's, and the worker keeps running. **Interact** is the session itself —
    the tmux terminal the work is happening in. A view that named only the first
    would leave the owner at the edge of the thing they asked to enter.
    """
    session = (task.session or {}).get("name") if isinstance(task.session, dict) else None
    label = f"{task.name}---task ({task.id})" if task.name else task.id
    lines = [f"{label} — {task.state} — {agent.id}---agent",
             f"  {(task.goal or '')[:160]}"]
    if task.blocked_by:
        lines.append(f"  waiting on: {task.blocked_by}")
    lines.append(f"  guided (your word first): /{task.id} <instruction>")
    if session:
        lines.append(f"  interact (the session itself): tmux attach -t {session}"
                     f"   — Ctrl-b d hands it back")
    else:
        lines.append("  no session yet — start one: "
                     f"ai4science sarsi run {agent.id} {task.id}")
    return "\n".join(lines)


def _find_task(config, task_id: str):
    for agent, t in all_tasks(config):
        if t.id == task_id:
            return agent, t
    return None, None


def _task_slash(cmd: str, arg: str) -> str:
    """`/task` (every board) and `/tsk_…` (one task, guided)."""
    from ai4science.harness.agents.sarsi import registry as reg
    try:
        config = reg.load()
    except reg.ConfigError:
        return ("no sarsi registry on this machine yet — "
                "set one up with: ai4science sarsi init")
    except Exception as e:
        return f"could not read the sarsi registry: {e}"

    if cmd == "task":
        rows = all_tasks(config)
        if not rows:
            return "no tasks on this machine yet — /<agent> do <goal> starts one"
        # The NAME is the row's handle — `/write-fib` opens it. The id still
        # exists (task view shows it); a board is for scanning, not quoting.
        return "\n".join(
            f"  {(t.name + '---task' if t.name else t.id):<26} "
            f"{t.state:<12} {a.id + '---agent':<28} "
            f"{(t.goal or '')[:50]}" for a, t in rows)

    agent, t = _find_task(config, cmd)
    if t is None:
        return (f"{cmd} is not a task on this machine — /task lists them")
    if not arg:
        return task_view(config, agent, t)

    # With words after it, this is guided steering: the owner's instruction goes
    # in ahead of whatever the worker would have said next.
    from ai4science.harness.agents.sarsi import session as ses
    try:
        ses.guide(config, agent, t, arg)
        return f"{t.id}: sent, ahead of the worker — {arg[:80]}"
    except Exception as e:
        return f"{t.id}: could not steer it — {e}"


def _sarsi_bridge(cmd: str, arg: str, agent_name: str) -> str:
    """`/do` and `/tasks` — the door from this chat agent to its sarsi worker.

    The chat agent answers in-process: ask it for an implementation and it
    writes one here. Its sarsi counterpart is the other contract — the agent
    you talk to does not execute, it opens a task, agrees a plan with
    `sarsi-claude`, and that session drives Claude Code.

    So this delegates and returns. It never runs the goal, and it never guesses
    which worker was meant: an agent with no counterpart gets the list, not a
    default. Every failure is a returned string — raising here would drop the
    REPL session the owner is standing in.
    """
    from ai4science.harness.agents.sarsi import registry as reg

    try:
        config = reg.load()
    except reg.ConfigError:
        return ("no sarsi registry on this machine yet — the seven agents are "
                "not configured.\n  set them up with: ai4science sarsi init")
    except Exception as e:                       # never take the REPL down
        return f"could not read the sarsi registry: {e}"

    agent = config.agents.get(agent_name)
    if agent is None:
        # Hostname is the display name for sarsi-machine [A21(b)] — resolve it.
        if agent_name == _machine_hostname():
            agent = config.agents.get("sarsi-machine")
    if agent is None:
        return (f"{agent_name or 'this agent'} has no sarsi worker — it answers "
                f"here instead of delegating.\n  workers with a task board: "
                f"{', '.join(sorted(config.agents))}\n"
                f"  switch with /agent <name>, then /do <goal>")

    from ai4science.harness.agents.sarsi import chat as sarsi_chat

    if cmd == "tasks":
        return sarsi_chat.handle(config, agent, "/tasks", surface="cli")

    if not arg:
        return (f"usage: /do <goal>  — hands {agent.id} a goal; it drafts a "
                f"plan and sarsi-claude agrees it before anything runs")

    from ai4science.harness.agents.sarsi import (plan as pl, task as tsk,
                                                 worker as wk)
    try:
        directive = wk.Directive(agent_id=agent.id, goal=arg)
        out = wk.admit(config, agent, directive)
    except (wk.BadDirective, wk.NotAWorker) as e:
        return str(e)
    if not out.admitted:
        return f"{out.message}\nnot queued — nothing is waiting on this"

    task = tsk.attach_plan(config, agent, tsk.create(config, agent, directive),
                           pl.draft(directive))
    task = tsk.start(config, agent, task)
    lines = [f"{agent.id} holds {task.id} — {task.state}",
             f"  plan drafted; sarsi-claude agrees it before work starts",
             f"  open it:    ai4science sarsi plan {agent.id} {task.id}",
             f"  run it:     ai4science sarsi run {agent.id} {task.id}"]
    if task.awaiting:
        lines.insert(1, f"  waiting on: {', '.join(task.awaiting)}")
    return "\n".join(lines)


def make_confirm(read_input, mode_label: str):
    """Per-edit confirmation with `a(lways)` (Claude Code / SDK-path parity).

    `read_input(prompt, mode)` supplies the answer (tui.read_input in the
    REPL; injectable for tests). Answering `a` allows THIS tool name for the
    rest of the session. NOTE: bash is confirm-gated because its `cmd` is NOT
    path-sandboxed (see permissions.py) — the human approval IS the bash
    sandbox in Plan 1 (read-only commands are auto-allowed by the gate and
    never reach here).
    """
    always: set = set()

    def _confirm(name: str, args: dict, preview: str) -> bool:
        if name in always:
            return True
        from ai4science.harness import tui
        options = ["Yes",
                   f"Yes, and don't ask again for {name} this session",
                   "No, and tell the agent what to do differently (esc)"]
        question = f"⏺ {name}\n  {preview}\n\nDo you want to proceed?"
        try:
            idx = tui.ask_choice(question, options,
                                 read_input=read_input, mode=mode_label or "chat")
        except EOFError:
            return False
        if idx == 1:                 # Yes, and don't ask again
            always.add(name)
            return True
        return idx == 0              # Yes (else No)

    return _confirm


def _clean_turn_error(exc) -> str:
    """One-line, human-readable turn error (no traceback)."""
    s = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {s}" if s else name


def _turn_cost_for(backend: str, model: str, usage):
    """(pwm, wallet) for one Usage — the same pricing path make_meter uses."""
    try:
        _src, _pid, wallet, mult = routing._select_source(backend)
        u = {"input": usage.input, "output": usage.output, "total": usage.total}
        cost = pricing.price_call(model, u, price_multiplier=mult)
        return float(cost.get("pwm") or 0.0), wallet
    except Exception:
        return 0.0, None


def _next_available_brand(current: Optional[str]):
    """First orchestration brand whose creds resolve and that isn't `current`.
    Returns (backend, model) or None. Used to self-heal when an auto-detected
    brand fails a turn (e.g. the default openai key 401s → fall back to gemini)."""
    from ai4science.harness.adapters.factory import harness_available
    for b, m in routing.AGENT_CHAINS.get("orchestration", []):
        if b != current and harness_available(b):
            return b, m
    return None


# The `/model` menu is AGENT-scoped, as (label, backend, model_id) entries:
#  • Vendor agents are locked to one provider — Claude → Anthropic, Codex → OpenAI
#    (keyed by the spec's default_backend).
#  • Every other agent gets the cross-provider flagship menu and can switch freely.
# Selecting an entry switches BOTH backend and model.
_LOCKED_MENU = {
    "anthropic": [("Opus 5", "anthropic", "claude-opus-5"),
                  ("Opus 4.8", "anthropic", "claude-opus-4-8"),
                  ("Sonnet 4.6", "anthropic", "claude-sonnet-4-6"),
                  ("Haiku 4.5", "anthropic", "claude-haiku-4-5")],
    "openai":    [("ChatGPT 5.5", "openai", "gpt-5.5"),
                  ("ChatGPT 5.5 Codex", "openai", "gpt-5.5-codex")],
}
_FLAGSHIP_MENU = [("Opus 5", "anthropic", "claude-opus-5"),
                  ("Opus 4.8", "anthropic", "claude-opus-4-8"),
                  ("ChatGPT 5.5", "openai", "gpt-5.5"),
                  ("Gemini 3.1 Pro", "gemini", "gemini-3.1-pro-preview")]

# Typed shortcuts (`/model haiku`, `/model gpt`, …) → model id, resolved within
# whatever menu the active agent allows.
_TYPED_ALIASES = {
    "opus": "claude-opus-5", "opus-5": "claude-opus-5",
    "opus-4-8": "claude-opus-4-8", "fable": "claude-opus-5",
    "sonnet": "claude-sonnet-4-6", "haiku": "claude-haiku-4-5",
    "gpt": "gpt-5.5", "chatgpt": "gpt-5.5", "gpt-5.5": "gpt-5.5", "gpt5.5": "gpt-5.5",
    "codex": "gpt-5.5-codex",
    "gemini": "gemini-3.1-pro-preview", "pro": "gemini-3.1-pro-preview",
}


def _agent_model_menu(spec):
    """(label, backend, model) options the given agent may use."""
    lock = getattr(spec, "default_backend", None)
    if lock:
        return _LOCKED_MENU.get(lock, _FLAGSHIP_MENU)
    return _FLAGSHIP_MENU


def _resolve_in_menu(menu, tok: str):
    """Resolve a typed token (alias / id / label) to a (backend, model) IN this
    agent's menu, or None if it isn't allowed for this agent.

    Also handles two-token form: `/model openai gpt-5.5` → (backend, model_id)."""
    tl = (tok or "").strip().lower()
    want = _TYPED_ALIASES.get(tl, tok)
    for lbl, be, mid in menu:
        if mid == want or mid.lower() == tl or lbl.lower() == tl:
            return (be, mid)
    # Two-token form: "openai gpt-5.5" — split on first space
    if " " in tl:
        be_part, mid_part = tl.split(None, 1)
        for lbl, be, mid in menu:
            if be.lower() == be_part and (mid.lower() == mid_part or mid == mid_part):
                return (be, mid)
    return None


def _infer_backend(model: str) -> Optional[str]:
    """Guess the backend from a model id. Exact AGENT_CHAINS match first, then a
    substring heuristic — so `--model gemini-3.1-pro-preview` selects gemini."""
    for chain in routing.AGENT_CHAINS.values():
        for b, m in chain:
            if m == model:
                return b
    ml = model.lower()
    for needle, b in (("gemini", "gemini"), ("gpt", "openai"), ("claude", "anthropic"),
                      ("deepseek", "deepseek"), ("qwen", "qwen")):
        if needle in ml:
            return b
    return None


def _pick_brand(backend: Optional[str], model: Optional[str]):
    """Return (backend, model) using the orchestration pool or explicit override.

    Priority:
      1. Both backend and model explicitly supplied → use as-is.
      2. Only backend supplied → first model in AGENT_CHAINS for that backend,
         or a sensible default.
      3. Neither → walk AGENT_CHAINS["orchestration"] and pick the first brand
         whose creds are present (harness_available); fall back to
         ("gemini", "gemini-3.1-pro-preview").
    """
    if backend and model:
        return backend, model

    if backend:
        # Find the model for this backend in the orchestration chain.
        for b, m in routing.AGENT_CHAINS.get("orchestration", []):
            if b == backend:
                return backend, m
        # Backend not in orchestration chain — use a default model.
        return backend, "claude-opus-5"

    if model:
        # Only a model id given — infer its backend so `--model gemini-…` works.
        inferred = _infer_backend(model)
        if inferred:
            return inferred, model

    # Auto-detect: first reachable backend in the orchestration chain.
    from ai4science.harness.adapters.factory import harness_available
    for b, m in routing.AGENT_CHAINS.get("orchestration", []):
        if harness_available(b):
            return b, m

    # Nothing reachable — fall back to Gemini.
    return "gemini", "gemini-3.1-pro-preview"


# NOTE: legacy/unused at runtime — research mode's LIVE system prompt is
# AgentSpec.system_prompt in ai4science/harness/agents/specs/research.py (resolved
# via agent_registry.get("research")). Edit THAT to change research behavior.
# Kept only because a test still imports this symbol.
RESEARCH_PROMPT = (
    "You are AI4Science in RESEARCH mode. In addition to coding tools, you can query "
    "the PWM registry: pwm_principles / pwm_principle, pwm_benchmarks / pwm_benchmark, "
    "pwm_solutions (registered SOTA solutions + scores per benchmark), pwm_overview. "
    "Use registered Principles, Specs, Benchmarks and Solutions to ground your work — "
    "consult pwm_solutions before proposing a new solution, and build on the best "
    "registered baselines. Mainnet/testnet status is shown via each artifact's chain_status."
)


def _make_build_context(*, workspace, brand_provider, session_factory=None,
                        read_only=False, auto_yes=False, mcp_clients=None,
                        writable_roots=None) -> BuildContext:
    return BuildContext(workspace=workspace, brand_provider=brand_provider,
                        session_factory=session_factory, read_only=read_only,
                        auto_yes=auto_yes, mcp_clients=mcp_clients,
                        writable_roots=writable_roots)


def _registry_for_spec(spec, *, is_subagent, ctx):
    return build_registry_for(spec, is_subagent=is_subagent, ctx=ctx)


def _format_mode_menu() -> str:
    from ai4science.harness import tui as _tui
    lines = ["[agents]"]
    for s in agent_registry.core_agents():
        lines.append(f"  {s.name:<22} {s.description}")
    n = len(agent_registry.specific_agents())
    lines.append(f"  {'specific':<22} ({n}) domain agents — /agent specific <query> to search")
    lines.append("  switch with: /agent <name> (e.g. /agent Claude, /agent \"Computational Imaging\")")
    return "\n".join(lines)


def _format_specific_list(query: str) -> str:
    hits = agent_registry.search(query)
    if not hits:
        return f"[agents] no specific agent matches {query!r}"
    return "\n".join([f"  {s.name:<24} {s.title}" for s in hits])


def build_common_registry(*, workspace, session_factory, enable_pwm=True,
                          enable_subagents=True, mcp_clients=None):
    """Assemble core ∪ PWM ∪ sub-agent ∪ MCP tool registry.

    Parameters
    ----------
    workspace:
        Directory passed to tools that need a workspace path.
    session_factory:
        Callable used by the ``task`` sub-agent tool to spawn child sessions.
    enable_pwm:
        If True, add the four deterministic PWM tools (pwm_status, etc.).
    enable_subagents:
        If True, add the ``task`` delegation tool.
    mcp_clients:
        Optional list of stdio MCP client objects whose tools are merged in.
    """
    from ai4science.harness.tools import default_registry
    reg = default_registry()
    if enable_pwm:
        from ai4science.harness import mcp_pwm
        for t in mcp_pwm.pwm_tools():
            reg.add(t)
    if enable_subagents:
        from ai4science.harness.subagents import make_task_tool
        reg.add(make_task_tool(session_factory=session_factory, depth=0))
    for client in (mcp_clients or []):
        from ai4science.harness.mcp_client import mcp_tools
        for t in mcp_tools(client):
            reg.add(t)
    return reg


def build_research_registry(*, workspace, session_factory, enable_pwm=True,
                            enable_subagents=True, mcp_clients=None):
    """Assemble the research registry: common core + PWM data tools.

    The research tools (pwm_solutions, pwm_principles, etc.) are added on top
    of the common registry.  Common mode does NOT get these — that's the moat.
    """
    reg = build_common_registry(workspace=workspace, session_factory=session_factory,
                                enable_pwm=enable_pwm, enable_subagents=enable_subagents,
                                mcp_clients=mcp_clients)
    from ai4science.harness.research_tools import research_tools
    for t in research_tools():
        reg.add(t)
    return reg


def run_common_repl(
    workspace: Path,
    *,
    read_only: bool = False,
    auto_yes: bool = False,
    backend: Optional[str] = None,
    model: Optional[str] = None,
    on_text=None,
    resume_history: Optional[List[Message]] = None,
    session_id: Optional[str] = None,
    writable_roots: Optional[List[Path]] = None,
    system_prompt: Optional[str] = None,
    mode_label: str = "unified-LLM",
    intro: Optional[str] = None,
) -> None:
    """Run the native-harness REPL until EOF or /exit.

    Parameters
    ----------
    workspace:
        Directory the agent can read/write (subject to read_only).
    read_only:
        If True, mutating tools are blocked at the permission gate.
    auto_yes:
        If True, all tool calls are auto-approved (no prompt).
    backend:
        Override the LLM backend (e.g. "anthropic", "openai", "gemini").
        None → auto-picked from the orchestration chain.
    model:
        Override the model id.  None → picked alongside backend.
    on_text:
        Callable[[str], None] invoked for each text delta.  Defaults to
        writing to stdout without a newline.
    resume_history:
        Prior conversation history to seed into the session (from
        persistence.load()).  None → fresh session.
    session_id:
        Stable id for this session used by persistence.save().
        None → a new random id is generated.
    system_prompt:
        Optional system prompt string seeded as the leading system Message in
        history.  None → no system turn added.
    intro:
        Optional plain-text block printed once after the session banner, before
        the first prompt (e.g. the Manager's login greeting).  None → nothing.
    """
    from ai4science.harness import persistence

    # Shining-star spinner (Claude Code feel): pulses while the model is
    # thinking; the first streamed token clears it. Holder is per-turn.
    from ai4science.harness.spinner import Spinner
    _spin = {"s": None}

    def _stop_spin() -> None:
        if _spin["s"] is not None:
            _spin["s"].stop()
            _spin["s"] = None

    # Live output-token estimate for the box's "↓ N tokens" status.
    _live_tok = {"n": 0}

    def _tick_tokens(t: str) -> None:
        _live_tok["n"] += max(1, len(t) // 4)   # ~4 chars/token
        from ai4science.harness import tui as _tui
        _tui.set_tokens(_live_tok["n"])

    if on_text is None:
        def on_text(t: str) -> None:
            _stop_spin()                  # first token → clear the spinner
            _tick_tokens(t)
            sys.stdout.write(t)
            sys.stdout.flush()
    else:
        _user_on_text = on_text
        def on_text(t: str) -> None:      # noqa: F811 — wrap caller's on_text
            _stop_spin()
            _tick_tokens(t)
            _user_on_text(t)

    # Per-edit confirmation with a(lways) (Claude-Code style). Skipped by the
    # gate when auto_yes or read_only; read-only bash is auto-allowed earlier.
    def _tui_read(prompt: str, mode: str) -> str:
        from ai4science.harness import tui
        return tui.read_input(prompt, mode)

    _confirm = make_confirm(_tui_read, mode_label)

    active_spec = agent_registry.get(mode_label) or agent_registry.get("unified-LLM")
    # A mode may prefer a backend (e.g. 'codex' → openai, 'claude-code' →
    # anthropic). Honor it only when the user pinned nothing, so an explicit
    # --backend/--model always wins.
    eff_backend = backend
    if eff_backend is None and model is None and active_spec.default_backend:
        eff_backend = active_spec.default_backend
    active_backend, active_model = _pick_brand(eff_backend, model)
    # The brand was truly auto-detected (self-heal allowed) only when nothing —
    # not even a mode default — pinned it. A mode that requires its backend
    # (codex) must not silently self-heal to a different brand.
    brand_autodetected = backend is None and model is None and eff_backend is None
    fell_back = {"v": False}

    # Mutable state dict — tracks modes and slash-command flags.
    # _build_session reads read_only/auto_yes from here so toggles take effect.
    state: dict = {
        "read_only": read_only,
        "auto_yes": auto_yes,
        "exit": False,
        # which agent is answering — `/do` delegates to the sarsi worker of
        # this name, so it has to follow `/agent` switches (see below).
        "agent": active_spec.name,
        # the console's Mode — None until the first `/<agent-name>` line
        # enters it; _prompt_for and console.route both default it themselves.
        "mode": None,
    }

    # Per-turn token accumulator (mutated by the meter wrapper).
    turn_tokens: dict = {"total": 0}
    turn_cost = {"pwm": 0.0, "wallet": None}
    turn_calls = {"n": 0}

    # Collapsed Claude Code-style tool lines (`⏺ bash(ls …)` / dim `⎿ …`).
    from ai4science.harness import toolfmt

    def _show_tool_start(name: str, args: dict) -> None:
        _stop_spin()
        turn_calls["n"] += 1
        from ai4science.harness import tui as _tui
        _tui.set_activity(f"running {toolfmt._DISPLAY_NAME.get(name, name)}")
        print(f"\n{toolfmt.fmt_tool_start(name, args)}", flush=True)

    def _show_tool_end(name: str, result: str) -> None:
        from ai4science.harness import tui as _tui
        _tui.set_activity("thinking")
        line = toolfmt.fmt_tool_result(result)
        if line:
            print(line, flush=True)
    gate = PwmGate.from_env()
    turn_counter = {"n": 0}
    # Agent-mining: domain tools invoked this turn (their authors earn from the
    # agent pool). Base Claude-Code tools are platform infra, not contributions.
    turn_tools: set = set()

    # Settled here rather than just before _build_session: the meter is filed
    # under this id, and it has to be the SAME one persistence.save() uses or
    # the ledger points at a session no workspace index maps to.
    _sid = session_id or secrets.token_hex(8)

    def _make_wrapped_meter(b: str, m: str):
        """Return a meter that accumulates into turn_tokens AND calls real meter."""
        real = make_meter(backend=b, model=m, session=_sid)

        def _meter(u) -> None:
            turn_tokens["total"] += getattr(u, "total", 0) or 0
            pwm, wallet = _turn_cost_for(b, m, u)
            turn_cost["pwm"] += pwm
            if wallet:
                turn_cost["wallet"] = wallet
            real(u)

        return _meter

    def _child_session_factory(*, spec, ctx):
        child = AgentSession(
            adapter=adapter_for(active_backend),
            model=active_model,
            backend=active_backend,
            workspace=workspace,
            writable_roots=writable_roots,
            read_only=state["read_only"],
            auto_yes=True,                      # sub-agents auto-approve
            confirm=_confirm,
            on_text=on_text,
            meter=_make_wrapped_meter(active_backend, active_model),
            on_tool=lambda name: turn_tools.add(name),
            on_tool_start=_show_tool_start, on_tool_end=_show_tool_end,
            registry=build_registry_for(spec, is_subagent=True, ctx=ctx),
        )
        if spec.system_prompt:
            child.history.insert(0, Message(role="system", content=spec.system_prompt))
        return child

    def _build_session() -> AgentSession:
        s = AgentSession(
            adapter=adapter_for(active_backend),
            model=active_model,
            backend=active_backend,
            workspace=workspace,
            writable_roots=writable_roots,
            read_only=state["read_only"],
            auto_yes=state["auto_yes"],
            confirm=_confirm,
            on_text=on_text,
            meter=_make_wrapped_meter(active_backend, active_model),
            on_tool=lambda name: turn_tools.add(name),
            on_tool_start=_show_tool_start, on_tool_end=_show_tool_end,
            registry=_registry_for_spec(
                active_spec, is_subagent=False,
                ctx=_make_build_context(
                    workspace=workspace,
                    brand_provider=lambda: (active_backend, active_model),
                    session_factory=_child_session_factory,
                    read_only=state["read_only"], auto_yes=state["auto_yes"],
                    writable_roots=writable_roots,
                )),
        )
        # Seed the system prompt on every build (initial AND /clear rebuild) so the
        # mode grounding survives a /clear and /mode switches re-ground.
        seed_prompt = active_spec.system_prompt or system_prompt
        if seed_prompt:
            s.history.insert(0, Message(role="system", content=seed_prompt))
        return s

    session = _build_session()

    if resume_history:
        session.history.extend(resume_history)

    from ai4science.harness.tui import _display_mode
    from ai4science import __version__ as _ver
    # Clean Claude-Code-style welcome header (coral accent), instead of noisy
    # [harness] log lines.
    _coral, _dim, _rst = "\x1b[38;5;173m", "\x1b[2m", "\x1b[0m"
    _friendly = {"claude-opus-5": "Opus 5",
                 "claude-opus-4-8": "Opus 4.8", "claude-sonnet-4-6": "Sonnet 4.6",
                 "claude-haiku-4-5": "Haiku 4.5", "gpt-5.5": "ChatGPT 5.5",
                 "gpt-5.5-codex": "ChatGPT 5.5 Codex",
                 "gemini-3.1-pro-preview": "Gemini 3.1 Pro"}
    _m = _friendly.get(active_model, active_model)
    _gate = ("gate on — turns charged in PWM" if gate.enabled else "gate off")
    # Login status: is a PWM token available? (env or saved account)
    def _signed_in() -> bool:
        import os as _os
        if _os.environ.get("PWM_TOKEN") or _os.environ.get("PWM_ONBOARD_TOKEN"):
            return True
        try:
            from ai4science import pwm_account
            return bool((pwm_account.load() or {}).get("token"))
        except Exception:
            return False
    _logged_in = _signed_in()
    _yellow = "\x1b[33m"
    print(f"\n{_coral}✷ ai4science{_rst} {_dim}v{_ver}{_rst}", flush=True)
    print(f"  {_dim}agent{_rst}  {_display_mode(mode_label)}  {_dim}·{_rst}  "
          f"{_m} {_dim}({active_backend}){_rst}", flush=True)
    print(f"  {_dim}cwd{_rst}    {workspace}", flush=True)
    print(f"  {_dim}tips{_rst}   /help · /agent · /model · /exit · Ctrl-C interrupts", flush=True)
    print(f"  {_dim}pwm{_rst}    {_dim}{_gate} · session {_sid} (resume: --resume {_sid}){_rst}",
          flush=True)
    # Remind logged-out users to sign in — when the gate is on, turns are blocked
    # ("could not verify your PWM balance") until they do.
    if not _logged_in:
        _why = ("turns are blocked until you sign in" if gate.enabled
                else "sign in to earn/spend PWM")
        print(f"  {_yellow}⚠ not signed in{_rst} {_dim}— run {_rst}{_coral}/login{_rst}"
              f"{_dim} (or `ai4science login`); {_why}.{_rst}", flush=True)
    print("", flush=True)
    # A one-time intro inside the session — the Manager greets the owner on login.
    if intro:
        print(intro, flush=True)
        print("", flush=True)

    from ai4science.harness import lineedit
    lineedit.enable(mode_label or "chat")     # ↑/↓ history, ←/→ cursor
    _interrupts = {"n": 0}
    while True:
        try:
            from ai4science.harness import tui
            _st = f"{active_model} · {_shortcwd(workspace)}"
            # use the CURRENT spec name so the info-line label tracks /mode switches
            line = tui.read_input(_prompt_for(state),
                                  active_spec.name or mode_label or "chat",
                                  _st).strip()
            _interrupts["n"] = 0
        except EOFError:
            print("\n[harness] EOF — exiting", flush=True)
            break
        except KeyboardInterrupt:
            _interrupts["n"] += 1
            if _interrupts["n"] >= 2:
                print("\n[harness] exiting", flush=True)
                break
            print("\n[harness] Ctrl-C — press again to exit (or type /exit)",
                  flush=True)
            continue

        # Accept bare exit words too (not only the slash form) — a user who
        # types `exit`/`quit`/`q` should not be sent to the LLM or trapped.
        if line.lower() in ("exit", "quit", "q", ":q", ":q!"):
            break

        # Every line is routed through the console first — it decides mode
        # transitions (`/sarsi-worker`, `/leave`), task creation and steering,
        # and the tmux hand-off, before the older slash chain ever sees the
        # line. An "answer" action means the console has nothing to add and
        # `_act.text` (possibly rewritten) falls through to that chain as-is.
        from ai4science.harness import console as _c
        _deps = _console_deps(state)
        _act, _new = _c.route(line, state.get("mode") or _c.Mode(), _deps)
        state["mode"] = _new
        if _act.kind != "answer":
            if _act.kind in ("say", "enter", "leave", "confirm"):
                if _act.text:
                    print(_act.text, flush=True)
                # Entering a worker: prime the LLM with a workspace briefing so
                # it "realises" it should look at its state before responding.
                # Injected as an ASSISTANT message — the agent says it self-checked.
                if _act.kind == "enter" and _new.kind == "agent":
                    _prime_worker_session(session, _new.name)
            elif _act.kind == "create":
                print(f"→ {_deps['create'](_act.agent, _act.goal, _act.backend)}",
                      flush=True)
            elif _act.kind == "guide":
                print(_deps["guide"](_act.task, _act.text), flush=True)
            elif _act.kind == "task-verb":
                print(_deps["task-verb"](_act.verb, _act.task, _act.text),
                      flush=True)
            elif _act.kind == "attach":
                _agent_id = _deps["pause_for_interact"](_act.task)
                print(_attach_tmux(_act.session, task=_act.task,
                                   agent=_agent_id), flush=True)
            continue
        line = _act.text
        _user_line = line  # original before workspace prefix — used for log

        # In agent mode (sarsi-worker) the LLM has no idea what tasks the worker
        # holds, what the standing task is, or what lessons are recorded. Prepend
        # a workspace snapshot so the answer is grounded in the actual state. [§12]
        #
        # How MUCH of it is routed per turn. This prefix used to be identical
        # for `hello` and for `implement M2`: the semantic store, the board,
        # the standing plan, both memory indexes, a live self-model probe and a
        # scored pass over the whole log, in front of every plain line typed.
        # `mode.route()` prices the turn first, and the gate assembles to that
        # price — the fast path of plan v3 §2.8, at the one call site that was
        # paying the full bill every time.
        _mode = state.get("mode")
        if (getattr(_mode, "kind", "") == "agent"
                and not line.startswith("/")):
            try:
                from ai4science.harness.agents.sarsi import (
                    registry as _sr, selfaware as _sa)
                _name = getattr(_mode, "name", "") or ""
                _ctx = ""
                try:
                    _cfg = _sr.load()
                    _wk = _cfg.agents.get(_name)
                    if _wk is not None:
                        _route = _turn_route(_cfg, _wk, line)
                        try:
                            _ctx = _sa.workspace_context(_cfg, _wk, surface="cli",
                                                         observation=line,
                                                         route=_route)
                        except _sa.ProtectedOverflow as _po:
                            # Fail closed, out loud. §7.2 says a consequential
                            # turn does not proceed with constraints missing,
                            # and the one thing worse than stopping is
                            # continuing with a context that quietly lost them.
                            print(f"[sarsi-worker] I am not acting on that yet: "
                                  f"{_po}", flush=True)
                            continue
                except Exception:
                    # No harness registry on this account -- most of this fleet.
                    # That must not cost the worker its workspace entirely: fall
                    # back to openclaw's, which needs only the agent id and is
                    # where the lessons actually live. Answering from none was
                    # the silent outcome before.
                    _ctx = ""
                if not _ctx and _name:
                    _ctx = _sa.openclaw_workspace_context(_name)
                if _ctx:
                    line = _ctx + line
            except Exception:
                pass

        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            cmd = cmd.lower().strip()
            arg = arg.strip()

            # /feedback — early-user feedback on the ACTIVE agent (agent-mining).
            if cmd == "feedback":
                if not arg:
                    print(f"[harness] usage: /feedback <your experience + how to improve "
                          f"{active_spec.name}>", flush=True)
                    continue
                # Zero-login: post_feedback auto-provisions a local wallet when
                # not logged in, so feedback always submits and can earn PWM.
                ok, status = gate.post_feedback(agent_name=active_spec.name, text=arg)
                note = (status if ok and str(status).startswith("accepted")
                        else status if any(str(status).startswith(k) for k in
                                           ("use_agent_first", "balance_not_low", "need_more_usage"))
                        else "program full (first-N guard)" if status == "program_full"
                        else f"failed ({status})")
                print(f"[pwm] feedback for {active_spec.name}: {note}", flush=True)
                continue

            # /login — sign in to physicsworldmodel.org mid-session (device flow)
            # so a logged-out or expired session can earn/spend PWM WITHOUT
            # restarting, then refresh the gate so the next turn uses the token.
            if cmd == "login":
                try:
                    from ai4science.commands.login import _login_pwm
                    _login_pwm(arg or None)        # arg = optional base/mirror url
                except (SystemExit, Exception):
                    pass                           # _login_pwm prints its own reason
                try:
                    fresh = PwmGate.from_env()   # PwmGate imported at module level
                    gate.token, gate.base, gate.enabled = (
                        fresh.token, fresh.base, fresh.enabled)
                except Exception:
                    pass
                continue

            # /whoami — show the current login / how the agent is powered.
            if cmd == "whoami":
                import os as _os
                try:
                    from ai4science import pwm_account
                    acct = pwm_account.load() or {}
                except Exception:
                    acct = {}
                tok = (_os.environ.get("PWM_TOKEN") or _os.environ.get("PWM_ONBOARD_TOKEN")
                       or acct.get("token"))
                if tok:
                    who = (acct.get("email")
                           or (f"user #{acct.get('user_id')}" if acct.get("user_id") else "signed in"))
                    print(f"[pwm] signed in: {who}  ({acct.get('base') or 'physicsworldmodel.org'})",
                          flush=True)
                else:
                    print("[pwm] not signed in — /login to sign in (or set PWM_TOKEN).",
                          flush=True)
                continue

            # /model needs the live session — handle inline. The menu is scoped to
            # the active agent: Claude → Anthropic models, Codex → OpenAI models,
            # every other agent → cross-provider flagships (Opus 4.8 / ChatGPT 5.5
            # / Gemini 3.1 Pro). Selecting switches BOTH backend and model.
            if cmd == "model":
                from ai4science.harness import tui as _tui
                menu = _agent_model_menu(active_spec)
                if not arg:
                    # interactive ↑/↓/⏎ picker (like real Claude Code).
                    labels = [f"{lbl} ({mid})"
                              + ("  ← current" if (be == active_backend and mid == active_model) else "")
                              for lbl, be, mid in menu]
                    idx = _tui.select(
                        f"Select a model · {_tui._display_mode(active_spec.name)}", labels)
                    if idx is None:
                        print("[harness] (cancelled)", flush=True)
                        continue
                    new_backend, new_model = menu[idx][1], menu[idx][2]
                else:
                    hit = _resolve_in_menu(menu, arg.strip().strip('"').strip("'"))
                    if hit is None:
                        opts = ", ".join(lbl for lbl, _, _ in menu)
                        print(f"[harness] {_tui._display_mode(active_spec.name)} "
                              f"can use: {opts}", flush=True)
                        continue
                    new_backend, new_model = hit
                if new_backend == active_backend and new_model == active_model:
                    print(f"[harness] model unchanged: {active_model}", flush=True)
                    continue
                try:
                    session.set_brand(adapter_for(new_backend), new_model, new_backend)
                    session.meter = _make_wrapped_meter(new_backend, new_model)
                    active_backend, active_model = new_backend, new_model
                    # User chose this brand explicitly — stop auto-healing away from it.
                    brand_autodetected = False
                    print(f"[harness] switched model: {active_model} "
                          f"(backend={active_backend})", flush=True)
                except ValueError as e:
                    print(f"[harness] error: {e}", flush=True)
                continue

            # `/agents` lists AND switches, which is what someone typing it
            # expects. `/agent` and `/mode` stay as aliases: removing a command
            # people already use, to make a naming point, is a cost paid by the
            # user for the designer's tidiness.
            if cmd in ("agent", "agents", "mode"):
                from ai4science.harness import tui as _tui
                target = None
                if not arg:
                    # interactive ↑/↓/⏎ picker over ALL agents — core first, then
                    # the domain-specific agents (cancer, drug-design, …) so they
                    # are directly selectable, not hidden behind `specific <query>`.
                    core = agent_registry.core_agents()
                    specific = sorted(agent_registry.specific_agents(),
                                      key=lambda s: (s.order, s.name))
                    pick = list(core) + list(specific)
                    # The sarsi WORKERS belong in this list too. The owner
                    # opened `/agents`, read sixteen chat specs, and could not
                    # find `sarsi-worker` — the agent the machine is built
                    # around — because workers live in the other registry. That
                    # distinction is real and it is not the owner's problem.
                    from ai4science.harness import console as _c
                    workers = _sarsi_worker_choices()
                    entries = _c.agent_menu(
                        core=[(_tui._display_mode(s.name), s.description)
                              for s in core],
                        specific=[(_tui._display_mode(s.name), s.description)
                                  for s in specific],
                        workers=workers,
                        active=_tui._display_mode(active_spec.name))
                    idx = _tui.select("Select an agent",
                                      [e.label for e in entries])
                    if idx is None:
                        print("[harness] (cancelled)", flush=True)
                        continue
                    chosen = entries[idx]
                    if chosen.kind == "worker":
                        # Entering a worker is a different act from switching
                        # this repl's spec — same list, said out loud on the row.
                        state["mode"] = _c.Mode(kind="agent", name=chosen.name)
                        print(f"now addressing {chosen.name}", flush=True)
                        _prime_worker_session(session, chosen.name)
                        continue
                    # workers were prepended, so shift back into `pick`
                    target = pick[idx - len(workers)]
                else:
                    parts = arg.split(None, 1)
                    if parts[0] == "specific":
                        print(_format_specific_list(parts[1] if len(parts) > 1 else ""),
                              flush=True)
                        continue
                    # the agent name may be multi-word / quoted (e.g. "Computational
                    # Imaging"), so resolve the FULL argument, not just the first token.
                    name = arg.strip().strip('"').strip("'")
                    target = agent_registry.get(_tui.resolve_mode(name))
                    if target is None:
                        print(f"[agents] unknown agent {name!r}; /agent to list",
                              flush=True)
                        continue
                if target.name == active_spec.name:
                    print(f"[harness] agent unchanged: {_tui._display_mode(target.name)}",
                          flush=True)
                    continue
                active_spec = target
                state["agent"] = target.name       # `/do` follows the switch
                # Enforce the agent's provider lock: Codex → OpenAI (ChatGPT),
                # Claude → Anthropic. Switch the brand to that provider's flagship
                # so a Codex session never runs on Claude (and vice-versa). Other
                # agents are cross-provider and keep the current backend/model.
                _lock = getattr(target, "default_backend", None)
                if _lock and active_backend != _lock:
                    _, active_backend, active_model = _agent_model_menu(target)[0]
                    brand_autodetected = False
                    print(f"[harness] backend → {active_backend} (model {active_model})",
                          flush=True)
                session = _build_session()
                # keep the full-TUI info line ("ai4science · <agent>") in sync
                _scr = getattr(_tui, "_ACTIVE", {}).get("screen")
                if _scr is not None:
                    _scr.mode = target.name
                print(f"[harness] switched agent: {_tui._display_mode(target.name)}",
                      flush=True)
                continue

            # /cost needs the live session's ledger — handle inline.
            if cmd == "cost":
                try:
                    from ai4science.llm import ledger
                    summary = ledger.summary()
                    print(f"[harness] cost: {summary}", flush=True)
                except Exception as e:
                    print(f"[harness] cost unavailable: {e}", flush=True)
                continue

            # /files lists workspace files — handle inline.
            if cmd == "files":
                try:
                    entries = sorted(os.listdir(workspace))
                    if entries:
                        print("[harness] workspace files:", flush=True)
                        for name in entries:
                            print(f"  {name}", flush=True)
                    else:
                        print("[harness] workspace is empty", flush=True)
                except Exception as e:
                    print(f"[harness] files error: {e}", flush=True)
                continue

            # /mcp describes MCP wiring status.
            if cmd == "mcp":
                print("[harness] MCP servers: none configured "
                      "(stdio MCP wiring is config-driven; see harness/mcp_client.py)",
                      flush=True)
                continue

            # All other slash commands go through the stateless dispatcher.
            handled, msg = _dispatch_slash(line, state)
            if msg:
                print(f"[harness] {msg}", flush=True)
            if state["exit"]:
                break
            if state.get("clear"):
                state["clear"] = False
                session = _build_session()
            elif handled and cmd in ("readonly", "yes", "default"):
                # Mode toggle — update the gate IN PLACE so the new modes take
                # effect without wiping conversation history (rebuilding the
                # session would reset history to []).
                session.gate.read_only = state["read_only"]
                session.gate.auto_yes = state["auto_yes"]
            if not handled:
                # An unknown slash used to fall through to the LLM as literal
                # text. That was generous in the wrong direction: a slash
                # addresses the HARNESS, and forwarding it silently turns a typo
                # into a paid turn whose output looks like an answer. It is only
                # refused when it LOOKS like a command — a prompt that begins
                # with a path is still a prompt.
                if looks_like_command(line):
                    print(f"[harness] {slash_answer(line)}", flush=True)
                    continue
            else:
                continue

        # Normal turn.
        from ai4science.harness import mentions
        allowed, _greason = gate.check()
        if not allowed:
            print(_greason, flush=True)
            continue
        turn_cost["pwm"] = 0.0
        turn_cost["wallet"] = None
        turn_tools.clear()
        turn_counter["n"] += 1
        text, images = mentions.expand(line, workspace)
        _history_len_before_turn = len(session.history)  # snapshot for fallback rollback

        def _do_turn():
            import time
            from ai4science.harness import interrupt
            from ai4science.harness import tui as _tui
            interrupt.clear()                   # stale Esc must not kill this turn
            turn_tokens["total"] = 0
            turn_calls["n"] = 0
            _live_tok["n"] = 0
            t0 = time.monotonic()
            _tui.begin_turn()                   # start the live "shining" status
            _spin["s"] = Spinner("thinking").start()   # shine until first token
            try:
                result = session.run_turn(text, images=images)
            finally:
                _stop_spin()
                _tui.end_turn()
            # Ensure there's a trailing newline after streamed output.
            if result and not result.endswith("\n"):
                print(flush=True)
            elapsed = time.monotonic() - t0
            print(toolfmt.fmt_turn_footer(seconds=elapsed,
                                          tools=turn_calls["n"],
                                          tokens=turn_tokens["total"]), flush=True)
            # One-sentence recap after substantial turns (Claude Code parity).
            # Decoration only — any failure is swallowed.
            from ai4science.harness import recap as recap_mod
            if recap_mod.should_recap(seconds=elapsed, tools=turn_calls["n"]):
                try:
                    rtext = recap_mod.generate_recap(
                        session.adapter, session.model,
                        user_text=text, final_text=result or "",
                        meter=session.meter)
                    if rtext:
                        print(f"\x1b[2m✶ recap: {rtext}\x1b[0m", flush=True)
                except Exception:
                    pass
            persistence.save(_sid, workspace, session.history)
            # §12: log REPL exchanges in agent mode so workspace_context() can
            # surface them as "recent exchanges" in future turns.
            _rmode = state.get("mode")
            if getattr(_rmode, "kind", "") == "agent" and result:
                try:
                    from ai4science.harness.agents.sarsi import (
                        registry as _sr, log as _log)
                    _rcfg = _sr.load()
                    _rwk = _rcfg.agents.get(getattr(_rmode, "name", "") or "")
                    if _rwk is not None:
                        _log.append(_rwk.agent_dir, "cli", _user_line, result)
                except Exception:
                    pass

        # Ctrl+C during a turn (inline/fallback mode = REPL on the main thread):
        # route SIGINT to the cooperative interrupt (like Esc / the TUI c-c
        # binding) so the turn ends and we return to the prompt for a NEW or
        # steering message — instead of a KeyboardInterrupt that exits the
        # program. Full-screen mode runs the REPL in a worker thread (signal
        # would fail there) and is handled by the TUI c-c binding, so guard on
        # the main thread. A 2nd Ctrl+C force-stops the turn.
        import signal as _signal
        import threading as _threading
        from ai4science.harness import interrupt as _intr
        _sigint = {"n": 0}

        def _sigint_handler(_signum, _frame):
            _intr.request()
            _sigint["n"] += 1
            if _sigint["n"] >= 2:
                raise KeyboardInterrupt        # 2nd press → hard-stop this turn
            print("\n[harness] interrupting… (Ctrl+C again to force-stop)", flush=True)

        _prev_sigint = None
        if _threading.current_thread() is _threading.main_thread():
            try:
                _prev_sigint = _signal.signal(_signal.SIGINT, _sigint_handler)
            except (ValueError, OSError):
                _prev_sigint = None
        try:
            _do_turn()
        except KeyboardInterrupt:
            _intr.clear()
            print("\n[harness] turn stopped — type a new message.", flush=True)
        except Exception as exc:
            # Walk the orchestration chain automatically: Opus 4.8 → GPT-5.5 →
            # Gemini (see routing.AGENT_CHAINS). If the primary model is
            # unavailable (overloaded, quota, no key), switch silently and retry
            # without interrupting the user.
            from ai4science.harness.adapters.factory import harness_available
            last = exc
            rest = [(b, m) for b, m in routing.AGENT_CHAINS.get("orchestration", [])
                    if (b, m) != (active_backend, active_model) and harness_available(b)]
            served = False
            for nb, nm in rest:
                print(f"\n[harness] {active_model} unavailable "
                      f"({_clean_turn_error(last)}) — switching to {nm}…", flush=True)
                active_backend, active_model = nb, nm
                session.set_brand(adapter_for(nb), nm, nb)
                session.meter = _make_wrapped_meter(nb, nm)
                # Roll back history to before the failed turn so run_turn()
                # doesn't append a duplicate user message on the retry.
                del session.history[_history_len_before_turn:]
                try:
                    _do_turn()
                    served = True
                    break
                except Exception as e2:
                    last = e2
            if not served:
                print(f"\n[harness] all models are temporarily unavailable "
                      f"({_clean_turn_error(last)}). Retry in a moment.", flush=True)
        finally:
            if _prev_sigint is not None:
                try:
                    _signal.signal(_signal.SIGINT, _prev_sigint)
                except (ValueError, OSError):
                    pass

        ok, _creason = gate.charge(turn_cost["pwm"], turn_cost["wallet"],
                                   purpose=f"ai4science:{active_spec.name}:{active_model}",
                                   idempotency_key=f"{_sid}:{turn_counter['n']}")
        if not ok:
            print(_creason, flush=True)

        # Agent-mining: log usage of any registered contribution (domain tool)
        # invoked this turn → its author earns a share of the agent pool. Off by
        # default; the backend attributes only registered contributions and is
        # idempotent per (contribution, turn).
        if gate.enabled and turn_tools:
            _tid = f"{_sid}:{turn_counter['n']}"
            for _name in turn_tools:
                if _name not in BASE_TOOLS:
                    gate.post_usage(contribution_id=_name, agent_name=active_spec.name,
                                    turn_id=_tid)

        # A line answered at the top level gets one note underneath naming the
        # worker that could take it as a task instead — and a tie prints
        # nothing, because a router that guesses is worse than one that is
        # quiet.
        if (state.get("mode") or _c.Mode()).kind == "top":
            _note = _console_deps(state)["suggest"](line)
            if _note:
                print(_note, flush=True)


def _install_agent_cmd(arg: str) -> str:
    """`/install-agent [name]` — market orientation (no arg) or install one."""
    import difflib as _dl
    from ai4science.harness import installed_agents as _ia
    try:
        from ai4science.harness.agents.sarsi import registry as _sreg
        config = _sreg.load()
        agents_dict = config.agents or {}
    except Exception:
        agents_dict = {}

    installed = _ia.load()

    # Collect all non-retired workers — initially all are popular [A27].
    all_workers = []
    for aid, agent in agents_dict.items():
        if getattr(agent, "role", "") != "worker":
            continue
        if getattr(agent, "retired", False):
            continue
        about = getattr(agent, "about", "") or ""
        if isinstance(about, (list, tuple)):
            about = " ".join(str(x) for x in about)
        all_workers.append((aid, str(about).strip()))

    if not arg:
        # Spec [A7]: market link → brief intro → usage → popular agents.
        lines = [
            "agent market: https://physicsworldmodel.org/agent",
            "",
            "The market lists research agents and tools you can add to your",
            "ai4science. An installed agent appears in /agent and is entered",
            "with /<agent-name>.",
            "",
            "  /install-agent <name>    install an agent",
            "  /uninstall-agent <name>  remove an installed agent",
            "",
        ]
        # Popular agents: director on `sarsi` decides; initially all are popular [A27].
        # No director query yet — degrade gracefully [A27b]: show full roster.
        if all_workers:
            lines.append("popular agents:")
            for aid, about in sorted(all_workers,
                                     key=lambda r: (r[0] not in installed, r[0])):
                marker = "✓" if aid in installed else " "
                line = f"  {marker} {aid}"
                if about:
                    line += f" — {about}"
                lines.append(line)
            lines.append("")
            lines.append("✓ = already installed")
        else:
            lines.append("(popular agent list unavailable — see market link above)")
        return "\n".join(lines)

    # Install by name.
    name = arg.lower()
    not_installed = {a[0].lower(): a[0] for a in all_workers if a[0] not in installed}
    installed_lower = {x.lower(): x for x in installed}
    if name in installed_lower:
        return f"install-agent: {installed_lower[name]} is already installed"
    if name not in not_installed:
        close = _dl.get_close_matches(name, sorted(not_installed), n=2, cutoff=0.6)
        hint = (" did you mean " + " or ".join(close) + "?") if close else ""
        return (f"install-agent: {name!r} not found.{hint} "
                f"/install-agent (no args) to browse the market")
    actual = not_installed[name]
    _ia.install(actual)
    return f"installed {actual} — it now appears in /agent  (enter it: /{actual})"


def _uninstall_agent_cmd(arg: str) -> str:
    """`/uninstall-agent [name]` — list installed (removable) or remove one."""
    from ai4science.harness import installed_agents as _ia
    installed = _ia.load()
    removable = sorted(installed - set(_ia._DEFAULT_INSTALLED))

    if not arg:
        if not removable:
            return ("uninstall-agent: no removable agents installed "
                    "(sarsi-worker is permanent)")
        lines = ["installed agents (removable):"]
        lines += [f"  {aid}" for aid in removable]
        lines.append("remove one: /uninstall-agent <name>")
        return "\n".join(lines)

    name = arg.lower()
    id_map = {aid.lower(): aid for aid in installed}
    if name not in id_map:
        return f"uninstall-agent: {name!r} is not installed"
    actual = id_map[name]
    if not _ia.uninstall(actual):
        return f"uninstall-agent: {actual} is a default agent and cannot be removed"
    return f"uninstalled {actual} — removed from /agent"


def _machine_hostname() -> str:
    """Short hostname — no domain suffix."""
    try:
        import socket
        return socket.gethostname().split(".")[0]
    except Exception:
        return "this-machine"


def _sarsi_worker_choices():
    """`(display_name, description)` for every installed sarsi agent.

    Workers are listed by their own id.  The machine agent (manager role) is
    listed by the machine's hostname per spec [A21(b)].  `sarsi-worker` sorts
    first; the machine agent sorts second.

    Returns `[]` on any failure — a machine with no sarsi registry still gets
    its spec list, and a broken registry must not take down the picker the
    owner is standing in.
    """
    try:
        from ai4science.harness.agents.sarsi import registry as reg
        config = reg.load()
    except Exception:
        return []
    hostname = _machine_hostname()
    rows = []
    for agent_id, agent in (config.agents or {}).items():
        if getattr(agent, "retired", False):
            continue
        if not getattr(agent, "installed", False):
            continue
        role = getattr(agent, "role", "")
        about = getattr(agent, "about", "") or ""
        if isinstance(about, (list, tuple)):
            about = " ".join(str(x) for x in about)
        about = str(about).strip()
        if role == "worker":
            rows.append((agent_id, about or "a sarsi worker: holds tasks and drives sessions"))
        elif role == "manager":
            # Machine agent shown by hostname [A21(b)].
            rows.append((hostname, about or "the machine agent — coordinates workers on this machine"))
    # sarsi-worker first, machine agent second, rest alphabetical.
    rows.sort(key=lambda r: (r[0] != "sarsi-worker", r[0] != hostname, r[0]))
    return rows


def _turn_route(config, agent, line: str):
    """Price this turn before assembling context for it. [plan v3 §7.0]

    Returns a `mode.Route`, or None when the router cannot be reached — in
    which case the gate falls back to its `ACTION` default, which is what every
    turn got before modes existed. Failing back to the expensive path is the
    right direction: the cheap path is an optimisation, and losing an
    optimisation is not the same kind of event as losing a safeguard.
    """
    try:
        from ai4science.harness.agents.sarsi import (discourse as _disc,
                                                     entry as _entry,
                                                     mode as _mode)
        try:
            cursor = bool(_entry.current(config, agent, surface="cli"))
        except Exception:
            cursor = False
        buf = _disc.recent(agent.agent_dir, "cli")
        return _mode.route(line, buf=buf, cursor=cursor)
    except Exception:
        return None


def _prime_worker_session(session, agent_name: str) -> None:
    """Prime the LLM session with a workspace briefing when entering agent mode.

    Injected as an ASSISTANT message so the LLM "realises" it has already
    looked at its own workspace before the user asks anything. Without this,
    the LLM has no inherent understanding that it should consult its task list,
    plans, memory, or history before responding.

    The message is short by design — one paragraph of instruction plus the
    workspace snapshot. A priming message that is too long would crowd out
    actual conversation history.
    """
    try:
        from ai4science.harness.agents.sarsi import registry as _sr, selfaware as _sa
        config = _sr.load()
        agent = config.agents.get(agent_name)
        if agent is None:
            return
        ctx = _sa.workspace_context(config, agent, surface="cli")
        briefing = (
            "I am sarsi-worker. My role is to manage tasks and guide sarsi-claude "
            "and sarsi-ai4sci — the agents that do the actual work. Every response "
            "I give must be grounded in the full history of this project, because "
            "the agents I direct depend on my decisions being consistent with "
            "everything agreed before. Before responding to anything, I always "
            "read the full conversation history and workspace state — task list, "
            "standing task plan, memory, and every past exchange — so nothing I "
            "say contradicts or ignores prior decisions.\n\n"
        )
        if ctx:
            briefing += ctx
        else:
            briefing += "(no tasks or history yet — workspace is empty)"
        session.history.append(Message(role="assistant", content=briefing))
    except Exception:
        pass


def _bridge_target(state: dict) -> str:
    """Which sarsi worker `/do` and `/tasks` act on.

    The mode FIRST. This passed `state["agent"]` — the chat spec — so the owner
    standing in `sarsi-worker ❯` typed `/tasks` and read "claude-code has no
    sarsi worker". The prompt said one thing and the command did another, which
    makes the mode label a lie rather than a safety mechanism.

    Only `kind == "agent"` counts: standing in a TASK is not standing in a
    worker, and there is no worker name to take from it. Falls back to the chat
    spec, which is the original behaviour and still right at the top.
    """
    mode = state.get("mode")
    if mode is not None and getattr(mode, "kind", "") == "agent":
        name = (getattr(mode, "name", "") or "").strip()
        if name:
            return name
    return state.get("agent") or ""
