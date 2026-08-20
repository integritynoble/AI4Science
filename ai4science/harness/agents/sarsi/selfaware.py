"""What a worker can truthfully say about itself.

`Agent.self_aware` has been a `bool` that `admin` reports and `playbook` lists
as an authority field, and that **nothing reads**. So a worker could not answer
"what am I, what may I do at this ceiling, what am I holding" — which is why
`can you plan at A2?` became a task goal instead of an answer. It had nothing to
answer *from*.

Modelled on the console's `web/selfmodel.py`, whose discipline is the whole
point:

    Claims are DERIVED AT READ TIME from stores that already exist … Nothing
    here fabricates: an empty store yields an honest "no verified outcomes
    recorded yet" claim.

So: every claim names the store it came from and its authority level, and a
worker with no history says it has none. **A self-model that narrates is worse
than no self-model** — it reads like evidence, and `workspace.py` already says
the same thing about history ("narration standing in for history … it reads
like evidence and it is not").

Two things this deliberately will not do:

  * **It will not report a permission the agent does not have.** The registry
    states what an agent WANTS; the trust ledger decides what it GETS, so a
    worker configured A3 and running at A2 reports both, and says which is
    real. Describing the request as the fact is how a self-model becomes a lie.
  * **It will not claim to execute.** The agent you talk to does not execute —
    it opens a task, agrees a plan, and a session does the work. A self-model
    that forgets that is the one that matters.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ai4science.harness.agents.sarsi.registry import Agent, Config

#: The evidence hierarchy, from the console's `selfmodel.py` and the
#: evidence-linked self-models paper. Per field, only sources at or above the
#: required authority may write; anything else is a provisional hypothesis.
AUTHORITY_NAMES = {
    1: "signed-governance-metadata",    # identity, owner, permissions
    2: "runtime-instrumentation",       # tasks held, tools, session state
    3: "independent-eval",              # benchmarks
    4: "audited-task-outcome",          # verdicts a verifier gave
    5: "owner-declaration",             # what the owner has said
    6: "model-inference",               # provisional
    7: "self-narrated",                 # recorded, never a source of truth
}

#: What each ceiling actually permits, read off `machine/session.py`'s decision
#: table rather than restated from memory — "A2" answers nothing on its own, and
#: the owner asking "can you plan at A2?" wanted the second half.
#: Each entry stands alone. "everything A1 allows" is a REFERENCE, not an
#: answer — an owner reading it still does not know what that is, and the whole
#: reason this field exists is that the letter alone answers nothing.
PERMITS = {
    "A0": "read files. Every write, command and network call stops for you",
    "A1": "read files, write inside the paths the plan declared, use the "
          "network, and run or test the project. A consequential command "
          "(git push, pip install, sudo) stops for you",
    "A2": "read files, write inside the paths the plan declared, use the "
          "network, run or test the project, AND run consequential commands "
          "(git push, pip install, sudo) without stopping",
    "A3": "read files, write inside declared paths, use the network, run and "
          "test, run consequential commands, and run commands it cannot "
          "classify — nothing stops for you",
}


def _claim(field: str, value: Any, level: int, store: str,
           provenance: str) -> Dict[str, Any]:
    """One evidence-linked claim. A claim with no provenance is a sentence, and
    a sentence that looks like evidence is the failure mode this avoids."""
    return {"field": field, "value": value, "authority_level": level,
            "authority": AUTHORITY_NAMES.get(level, f"L{level}"),
            "store": store, "provenance": provenance}


def claims(config: Config, agent: Agent) -> List[Dict[str, Any]]:
    """Everything this worker can say about itself, each linked to its store.

    Derived at read time. Nothing is cached, because a cached self-model is a
    claim about the past wearing the present tense.
    """
    out: List[Dict[str, Any]] = [
        _claim("id", agent.id, 1, "registry", "sarsi.json, the agent's own entry"),
        _claim("role", agent.role, 1, "registry", "sarsi.json"),
        _claim("owner", config.owner_id, 1, "registry",
               "the only id whose messages are honoured"),
        _claim("ceiling", agent.ceiling, 1, "registry",
               "what this agent is configured to ask for"),
    ]

    # What it actually gets. The registry states the request; the trust ledger
    # decides. Reporting the request as the fact is how a self-model lies.
    effective, why = _effective(agent.ceiling)
    out.append(_claim("effective_ceiling", effective, 1, "trust-ledger", why))
    out.append(_claim("permits", PERMITS.get(effective, "unknown"), 1,
                      "governance", "the decision table in machine/session.py"))

    out.append(_claim("tools", list(agent.tools or []), 1, "registry",
                      "declared for this agent; a task may declare more"))
    # A BOOL, not a list — checked rather than assumed. A self-model that
    # reports the wrong shape of its own permissions is the exact failure this
    # module exists to prevent.
    out.append(_claim("standing_grants", bool(agent.standing_grants), 1,
                      "registry",
                      "whether this agent may act on grants given once, "
                      "rather than per task"))

    held, states = _tasks(config, agent)
    out.append(_claim("tasks", held, 2, "task-store",
                      "counted now, not remembered"))
    if states:
        out.append(_claim("task_states", states, 2, "task-store",
                          "what each is waiting for"))

    # L4 — what it has been VERIFIED to do, not what it did. This was the gap
    # the module shipped with: it could say what the worker IS and what it is
    # HOLDING, and not what it has PROVEN, while every verdict sat on disk
    # unread. `None` when nothing has been judged — never a zero, because "never
    # seen it work" and "seen it fail" are different claims.
    from ai4science.harness.agents.sarsi import competence as _comp
    est = _comp.competence(config, agent)
    out.append(_claim("proven", _comp.render(est), 4, "verdicts",
                      ("%d judged task(s); %d judged by the engine that did the "
                       "work" % (est["n"], est.get("self_judged", 0)))
                      if est else "no task has been judged yet"))

    # L3 — how well-calibrated it is. Distinct from L4: `proven` says what it
    # has achieved, this says whether its own confidence can be trusted. A
    # worker that succeeds 70% and says 70% is more useful than one that
    # succeeds 90% and claims 100%, because only the first can be planned
    # around. `None` when nothing was predicted before it was judged.
    from ai4science.harness.agents.sarsi import forecast as _fc
    cal = _fc.calibration(config, agent)
    out.append(_claim("calibration", _fc.render(cal), 3, "forecasts",
                      ("%d forecast(s) made before the verdict" % cal["n"])
                      if cal else "nothing has been predicted before it was judged"))

    out.append(_claim("executes", False, 1, "design",
                      "the agent you talk to does not execute: it opens a "
                      "task, agrees a plan, and a session does the work"))
    return out


def _effective(configured: str):
    """The ceiling the ladder will actually honour, and why."""
    try:
        from ai4science.harness.agents.machine import trust
        got = trust.effective_ceiling(configured)
        if got != configured:
            return got, (f"{configured} is earned, not set — capped to {got} "
                         f"until the trust ledger unlocks it")
        return got, "honoured as configured"
    except Exception:
        # Fail honest: say the ledger could not be read rather than assert the
        # configured value as if it had been checked.
        return configured, "the trust ledger could not be read; this is the "\
                           "CONFIGURED value, not a verified one"


def _tasks(config: Config, agent: Agent):
    try:
        from ai4science.harness.agents.sarsi import task as tsk
        rows = [t for t in tsk.all_of(config, agent)]
        return len(rows), {t.id: t.state for t in rows}
    except Exception:
        return 0, {}


def describe(config: Config, agent: Agent) -> str:
    """The claims as something an owner can read, or "" when the agent is not
    self-aware.

    The flag is honoured rather than ignored: it existed, was reported by
    `admin`, listed by `playbook` as an authority field, and read by nothing.
    A flag nobody reads is a claim nobody keeps.
    """
    if not getattr(agent, "self_aware", False):
        return ""

    by = {c["field"]: c for c in claims(config, agent)}
    ceiling = by["ceiling"]["value"]
    effective = by["effective_ceiling"]["value"]
    held = by["tasks"]["value"]

    lines = [f"I am {by['id']['value']}, a {by['role']['value']} on this machine."]

    if effective != ceiling:
        lines.append(f"My ceiling is configured {ceiling} but I actually run at "
                     f"{effective} — {by['effective_ceiling']['provenance']}.")
    else:
        lines.append(f"I run at ceiling {effective}.")
    lines.append(f"At {effective} I may: {by['permits']['value']}.")
    lines.append("While PLANNING I drop to A0 regardless — reads only — because "
                 "the plan is what you have not yet seen.")

    lines.append("")
    if held:
        states = by.get("task_states", {}).get("value") or {}
        lines.append(f"I am holding {held} task(s):")
        for tid, state in list(states.items())[:8]:
            lines.append(f"  {tid} — {state}")
        if len(states) > 8:
            lines.append(f"  … and {len(states) - 8} more — /tasks lists them")
    else:
        lines.append("I am holding no tasks right now.")

    tools = by["tools"]["value"]
    lines.append("")
    lines.append(f"Tools declared for me: {', '.join(tools) if tools else 'none'}.")
    if by["standing_grants"]["value"]:
        lines.append("I may act on standing grants — permissions you gave once "
                     "rather than per task.")
    else:
        lines.append("I have no standing grants: every permission is granted "
                     "per task, on the plan you read.")

    lines.append("")
    lines.append(f"What I have been verified to do: {by['proven']['value']}.")
    lines.append(f"How far my own confidence can be trusted: "
                 f"{by['calibration']['value']}.")

    lines.append("")
    lines.append("I do not execute anything myself. I open a task, agree a plan "
                 "with you, and a session does the work — sarsi-claude runs "
                 "Anthropic's claude binary, sarsi-ai4sci runs ai4science.")
    return "\n".join(lines)


#: Words that make a question about THIS AGENT rather than about the world.
#: Deliberately narrow: a router that guesses is worse than one that is quiet,
#: and a question this cannot answer from its own state must reach the model
#: rather than a canned page.
_SELF = ("you", "your", "yours", "yourself", "i am", "am i")
_ABOUT = ("ceiling", "a0", "a1", "a2", "a3", "permission", "grant", "task",
          "tasks", "plan", "backend", "tool", "tools", "who", "what", "which",
          "can", "may", "able", "holding", "doing", "role", "agent")


def _lessons_from(indexes) -> list:
    """The lesson lines of every MEMORY.md given, deduped, in order.

    One reader for both callers. The registry-free path and the full
    `workspace_context` used to carry a private copy of this filter each; two
    copies of a rule about what counts as a lesson is one copy too many, and
    the worker would have answered differently depending on which door it came
    through.

    A file that will not open loses only itself, never the others.
    """
    out, seen = [], set()
    for idx in indexes:
        try:
            if not idx.exists():
                continue
            text = idx.read_text().strip()
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line in seen:      # the same lesson in both trees is ONE lesson
                continue
            seen.add(line)
            out.append(line)
    return out


def openclaw_workspace_context(agent_id: str) -> str:
    """The workspace snapshot obtainable with NOTHING but an agent id.

    The full `workspace_context` needs the harness registry
    (`~/.sarsi/sarsi.json`) to resolve tasks and plans -- and that registry is
    absent on most accounts of this fleet, where the REPL's caller swallows the
    resulting error and adds no context at all. Silently: no lessons, no board,
    no warning.

    openclaw's workspace needs no registry. It is keyed by agent id alone, it
    exists wherever the agent does, and it is where this fleet's lessons are
    actually written. So a worker with no harness state still answers with its
    charter and its experience rather than with none.

    Returns "" when there is nothing to say, so a caller can concatenate it
    unconditionally.
    """
    import os
    from pathlib import Path
    ws = (Path(os.path.expanduser("~")) / ".openclaw"
          / ("workspace-" + str(agent_id or "")))
    lessons = _lessons_from([ws / "MEMORY.md"])
    if not lessons:
        return ""
    body = "memory (lessons):\n" + "\n".join(f"  {l}" for l in lessons[:8])
    return "[sarsi-worker workspace]\n" + body + "\n[/workspace]\n\n"


def _memory_indexes(config: Config, agent: Agent) -> list:
    """Every MEMORY.md this worker might have, harness tree first.

    Harness first because it is the one this process writes; openclaw's is
    read as a peer rather than a fallback -- on most accounts it is the only
    one that exists, and on this fleet it is the one with the lessons in it.
    """
    out = []
    try:
        from ai4science.harness.agents.sarsi import memory as _mem
        out.append(_mem.index_path(config, agent))
    except Exception:
        pass
    try:
        import os
        from pathlib import Path
        out.append(Path(os.path.expanduser("~")) / ".openclaw"
                   / ("workspace-" + str(getattr(agent, "id", ""))) / "MEMORY.md")
    except Exception:
        pass
    return out


def workspace_context(config: Config, agent: Agent, surface: str = "cli") -> str:
    """A compact workspace snapshot to prepend to LLM answers in agent mode.

    The LLM answering a question in sarsi-worker mode has no idea what tasks the
    worker holds, what the current standing task is, or what lessons the agent has
    recorded. This injects that context so the answer is grounded in the actual
    workspace rather than generic model knowledge.

    Returns "" when no context is available so the caller can skip the prefix.
    """
    parts: list = []

    # ── task board ─────────────────────────────────────────────────────────
    try:
        from ai4science.harness.agents.sarsi import task as tsk, entry as _entry
        rows = tsk.all_of(config, agent)
        standing_id = _entry.current(config, agent, surface=surface)
        if rows:
            board = ["tasks held:"]
            for t in rows[:6]:
                marker = " ← current" if t.id == standing_id else ""
                goal_snip = (t.goal or "")[:60]
                board.append(f"  {t.id}  [{t.state}]  {goal_snip}{marker}")
            if len(rows) > 6:
                board.append(f"  … {len(rows) - 6} more — /tasks lists them")
            parts.append("\n".join(board))
        else:
            parts.append("tasks held: none")
    except Exception:
        pass

    # ── standing task plan (brief) ──────────────────────────────────────────
    try:
        from ai4science.harness.agents.sarsi import task as tsk, entry as _entry
        standing_id = _entry.current(config, agent, surface=surface)
        if standing_id:
            t = tsk.get(config, agent, standing_id)
            if t:
                plan = tsk.read_plan(config, agent, t)
                if plan:
                    rendered = plan.render()
                    # keep first 400 chars — enough for context without overwhelming
                    snip = rendered[:400].strip()
                    if len(rendered) > 400:
                        snip += " …"
                    parts.append(f"current task plan ({standing_id}):\n{snip}")
    except Exception:
        pass

    # ── memory index, from BOTH workspaces ─────────────────────────────────
    # A sarsi-worker has two homes on this fleet and neither is wrong:
    #
    #   ~/.sarsi/agents/<id>/          the harness's — tasks, plans, memory/
    #   ~/.openclaw/workspace-<id>/    openclaw's    — AGENTS.md, MEMORY.md
    #
    # Reading only the first was silently half-blind: measured on a live
    # account the harness index did not exist while openclaw's held 29
    # lessons, so the worker could see WHAT it was doing and not WHAT IT HAD
    # LEARNED -- including lessons its own workspace wrote. A missing file is
    # not an error, so nothing reported it.
    #
    # Both are read. Which tree a lesson was written into is an accident of
    # the door the work came through, and the worker should not be made to
    # care.
    try:
        lesson_lines = _lessons_from(_memory_indexes(config, agent))
        if lesson_lines:
            parts.append("memory (lessons):\n" + "\n".join(
                f"  {l}" for l in lesson_lines[:8]))
    except Exception:
        pass

    # ── recent conversation log ─────────────────────────────────────────────
    try:
        from ai4science.harness.agents.sarsi import log as _log
        entries = _log.read(agent.agent_dir, surface, limit=4)
        if entries:
            log_lines = ["recent exchanges:"]
            for e in entries:
                ts = str(e.get("at", ""))[:16]
                inp = str(e.get("in", ""))[:60]
                out = str(e.get("out", ""))[:80]
                log_lines.append(f"  [{ts}] you: {inp}")
                log_lines.append(f"           worker: {out}")
            parts.append("\n".join(log_lines))
    except Exception:
        pass

    if not parts:
        return ""
    return "[sarsi-worker workspace]\n" + "\n\n".join(parts) + "\n[/workspace]\n\n"


def is_about_self(line: str) -> bool:
    """Is this a question the agent can answer from its own state?

    Both halves are required: a self word AND something it actually knows about
    itself. "what can you do" passes; "how does GAP-TV work" does not, and must
    not — answering it from a self-model would be a canned page standing in for
    a real answer.
    """
    text = (line or "").strip().lower()
    if not text:
        return False
    words = set(text.replace("?", " ").replace(",", " ").split())
    if not (words & set(_SELF) or any(p in text for p in ("i am", "am i"))):
        return False
    return bool(words & set(_ABOUT))
