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

from typing import Any, Dict, List, Optional

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
    per_source = []
    for idx in indexes:
        try:
            if not idx.exists():
                continue
            text = idx.read_text().strip()
        except Exception:
            continue          # one unreadable tree must not lose the other
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
        if lines:
            per_source.append(lines)

    # Round-robin, not concatenation. Concatenating meant the first tree's
    # lessons filled every slot the renderer had: a harness index with eight
    # lines would have hidden all 29 of openclaw's, silently undoing the whole
    # point of reading both. It does not bite on tina today only because tina
    # has no harness MEMORY.md at all -- luck, not design.
    out, seen = [], set()
    for row in range(max((len(c) for c in per_source), default=0)):
        for col in per_source:
            if row >= len(col):
                continue
            line = col[row]
            if line in seen:  # the same lesson in both trees is ONE lesson
                continue
            seen.add(line)
            out.append(line)
    return out


def _render_lessons(lessons: list, cap: int = 8) -> str:
    """The lessons block, saying so when it holds back.

    The task board has always announced its overflow ("... N more"); the
    memory block never did, so a truncated list of lessons read to the model
    exactly like a complete one -- 29 lessons on tina, 8 shown, and nothing
    anywhere saying the other 21 existed. A cap the reader cannot see is a
    quiet lie about what the worker knows.

    There is no /memory command to point at, so this names the file, which is
    real.
    """
    if not lessons:
        return ""
    shown = lessons[:cap]
    block = "memory (lessons):\n" + "\n".join(f"  {l}" for l in shown)
    if len(lessons) > cap:
        block += (f"\n  ... {len(lessons) - cap} more not shown -- "
                  f"MEMORY.md holds all {len(lessons)}")
    return block


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
    body = _render_lessons(_lessons_from([ws / "MEMORY.md"]))
    if not body:
        return ""
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


GATE_VERSION = "gate/4"


class ProtectedOverflow(Exception):
    """Owner constraints did not fit, on a turn that may not proceed without
    them. §7.2's fail-closed rule, raised rather than silently truncated."""

#: What each mode buys. Characters for the section caps (the assembler works in
#: text), tokens for the recent window (the buffer is token-budgeted). These are
#: defaults the gate RECORDS, not truths — §7.2 is explicit that a budget nobody
#: can see is not a budget.
#: The TOTAL each mode may spend, and what is held back for the model's own
#: answer. §7.2 specifies a whole-context budget with an output reserve, and
#: `MODE_BUDGET` below is per-section and in mixed units — so the sections
#: could each stay inside their own cap while the assembled context blew past
#: any total nobody was tracking. Measured: a CHAT turn with a 6000-token
#: recent budget produced a 21443-byte context.
CONTEXT_BUDGET = {
    "CHAT":   {"total_tokens": 8000,  "output_reserve": 2000},
    "REASON": {"total_tokens": 16000, "output_reserve": 4000},
    "ACTION": {"total_tokens": 32000, "output_reserve": 12000},
}

#: Trimmed in this order when the total is exceeded — cheapest evidence first.
#: `semantic` is absent on purpose: constraints are not trimmed, they fail
#: closed (§7.2), and the protected arm is what that rule protects.
TRIM_ORDER = ("episodic", "lessons", "plan", "board", "self", "recent")

#: Sections rendered oldest-first, where the END is the part worth keeping.
_TRIM_FROM_THE_FRONT = frozenset(("recent", "episodic"))

MODE_BUDGET = {
    "CHAT": {"recent_tokens": 6000, "episodic_chars": 0, "lessons": 0,
             "semantic": False, "self": "none", "plan": False},
    "REASON": {"recent_tokens": 3000, "episodic_chars": 1200, "lessons": 4,
               "semantic": "retrieved", "self": "cached", "plan": True},
    # ACTION carries recent dialogue too: §7.2 says "enough to resolve the
    # request", and a consequential turn is exactly where an unresolved `that`
    # is most expensive. It was 0 here, so the mode with the most at stake was
    # the only one with no short-term memory.
    "ACTION": {"recent_tokens": 2000, "episodic_chars": 3000, "lessons": 8,
               "semantic": "all-active", "self": "measured", "plan": True},
}


def workspace_context(config: Config, agent: Agent, surface: str = "cli",
                      observation: str = "", *, mode: str = "",
                      route: Any = None) -> str:
    """Working-memory gate — one assembler, three prices. [plan v3 §7.0-§7.4]

    `ACTION` (the default, and what every caller got before modes existed):

      1. Semantic memory  — all active entries; a constraint bypasses ranking
      2. Task board + intentional — plan for the standing task, current phase
      3. Memory lessons   — MEMORY.md from both workspaces
      4. Self model       — harness-observed fields, measured now, with staleness
      5. Episodic         — last 3 exchanges verbatim + scored older ones
      6. Log file path    — always shown, so the model can read further

    `REASON` buys the same shape smaller: cached self-model instead of a live
    probe, *retrieved* semantic memory instead of all of it, a tighter episodic
    slice scored against the resolved query.

    `CHAT` buys almost nothing: who I am, what I hold in one line, and the
    recent conversation. No live probe, no semantic store, no scored pass over
    the log, no plan. This is the fast path §2.8 exists for — and it is a
    *cost* decision only. Nothing about what the worker may do changes with the
    mode; the door still decides that, exactly where it did before.

    `observation` is the current user input, used to score relevance.
    `route` is a `mode.Route` — when given it supplies both the mode and the
    reference-resolved retrieval query, and it is recorded in the manifest so a
    routing mistake replays apart from a retrieval mistake.

    Returns "" when nothing is available, so the caller can skip the prefix.
    """
    picked = (mode or getattr(route, "mode", "") or "ACTION").upper()
    if picked not in MODE_BUDGET:
        picked = "ACTION"
    budget = MODE_BUDGET[picked]
    query = (getattr(route, "query", "") or observation or "")

    sections: list = []          # (name, text) in assembly order
    omitted: dict = {}           # category -> how many left out, never silent
    selected: dict = {}          # category -> ids that made it in

    def add(name: str, text: str) -> None:
        if text:
            sections.append((name, text))

    buf = None
    if budget["recent_tokens"]:
        try:
            from ai4science.harness.agents.sarsi import discourse as _disc
            buf = _disc.recent(agent.agent_dir, surface,
                               budget_tokens=budget["recent_tokens"])
            add("recent", _disc.render(buf))
            selected["exchanges"] = buf.ids()
            if buf.omitted:
                omitted["older_exchanges"] = buf.omitted
        except Exception:
            pass

    # ── semantic memory ────────────────────────────────────────────────────
    # ACTION injects every active entry: a constraint has no vocabulary in
    # common with the task it constrains, and ranking it is how it goes missing
    # exactly when it matters. REASON retrieves — and `retrieval.retrieve()`
    # keeps the protected arm unranked for the same reason.
    if budget["semantic"] == "all-active":
        try:
            from ai4science.harness.agents.sarsi import semantic as _sem
            text, rep = _sem.render_parts(config, agent)
            add("semantic", text)
            selected["semantic"] = [i for i in rep.get("ids", []) if i]
            if rep.get("omitted"):
                omitted["semantic"] = rep["omitted"]
                omitted["semantic_candidate_ids"] = _not_selected(
                    config, agent, selected["semantic"])
            if rep.get("protected_dropped"):
                # §7.2: for a consequential turn, constraints that do not fit
                # are NOT silently omitted. Proceeding would mean acting under
                # rules the model was never shown, which is the one omission
                # this gate exists to make impossible.
                raise ProtectedOverflow(
                    f"{rep['protected_dropped']} of {rep['protected_total']} "
                    f"owner constraints do not fit the context budget. This is "
                    f"an ACTION turn, so it stops here rather than proceeding "
                    f"without them — narrow the scope, or compact the "
                    f"constraint set, and say which.")
        except ProtectedOverflow:
            raise
        except Exception:
            pass
    elif budget["semantic"] == "retrieved":
        try:
            from ai4science.harness.agents.sarsi import retrieval as _ret
            task_id = _standing_id(config, agent, surface)
            got = _ret.retrieve(config, agent, query=query, task_id=task_id, k=6)
            add("semantic", _ret.render(config, agent, query=query,
                                        task_id=task_id, k=6))
            selected["semantic"] = [
                e.get("memory_id") or e.get("id", "")
                for e in (got.get("protected", []) + got.get("retrieved", []))]
            selected["retrieval_mode"] = got.get("mode", "")
            # §7.4 asks for the omitted CANDIDATE ids, not only a count: a
            # reader asking "why was that rule not applied?" needs to see that
            # it was a candidate and lost, which a number cannot say.
            missed = _not_selected(config, agent, selected["semantic"])
            if missed:
                omitted["semantic_candidate_ids"] = missed
            if got.get("error"):
                # `retrieve()` catches its own store failures and returns an
                # empty result, so this branch — not the except below — is how
                # a real failure becomes visible. Without it a turn that lost
                # every constraint to a corrupt store is byte-identical in the
                # audit record to a clean turn with no memory at all.
                omitted["semantic"] = f"retrieval failed: {got['error']}"
        except Exception as e:
            # Recorded, not swallowed. A turn answered without the memory it
            # asked for is a different event from a turn that had none, and
            # only the manifest can tell them apart afterwards. [§11.3]
            omitted["semantic"] = f"retrieval failed: {type(e).__name__}: {e}"

    # ── task board ─────────────────────────────────────────────────────────
    try:
        from ai4science.harness.agents.sarsi import task as tsk
        rows = tsk.all_of(config, agent)
        standing_id = _standing_id(config, agent, surface)
        if picked == "CHAT":
            # One line. Enough to know what it is holding without paying for
            # the board — "tasks held: 3 (current tsk_ab12) — /tasks lists them".
            if rows:
                cur = f" (current {standing_id})" if standing_id else ""
                add("board", f"tasks held: {len(rows)}{cur} — /tasks lists them")
                omitted["board_rows"] = len(rows)
            else:
                add("board", "tasks held: none")
        elif rows:
            board = ["tasks held:"]
            for t in rows[:6]:
                marker = " ← current" if t.id == standing_id else ""
                goal_snip = (t.goal or "")[:60]
                board.append(f"  {t.id}  [{t.state}]  {goal_snip}{marker}")
            if len(rows) > 6:
                board.append(f"  … {len(rows) - 6} more — /tasks lists them")
                omitted["board_rows"] = len(rows) - 6
            add("board", "\n".join(board))
            selected["tasks"] = [t.id for t in rows[:6]]
        else:
            add("board", "tasks held: none")
    except Exception:
        pass

    # ── standing task plan (brief) ──────────────────────────────────────────
    if budget["plan"]:
        try:
            from ai4science.harness.agents.sarsi import task as tsk
            standing_id = _standing_id(config, agent, surface)
            if standing_id:
                t = tsk.get(config, agent, standing_id)
                if t:
                    plan = tsk.read_plan(config, agent, t)
                    if plan:
                        rendered = plan.render()
                        snip = rendered[:400].strip()
                        if len(rendered) > 400:
                            snip += " …"
                            omitted["plan_chars"] = len(rendered) - 400
                        add("plan", f"current task plan ({standing_id}):\n{snip}")
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
    if budget["lessons"]:
        try:
            lessons = _lessons_from(_memory_indexes(config, agent))
            block = _render_lessons(lessons, cap=budget["lessons"])
            add("lessons", block)
            if len(lessons) > budget["lessons"]:
                omitted["lessons"] = len(lessons) - budget["lessons"]
        except Exception:
            pass

    # ── self model ─────────────────────────────────────────────────────────
    # `measured` runs the probes; `cached` reads the last measurement with its
    # staleness flags intact. A greeting does not pay for a probe, and a stale
    # field is still reported as stale rather than quietly refreshed.
    if budget["self"] != "none":
        try:
            from ai4science.harness.agents.sarsi import selfmodel as _sm
            if budget["self"] == "measured":
                _sm.sync(config, agent)
            add("self", _sm.render_cached(agent.agent_dir))
        except Exception:
            pass
    else:
        omitted["self_fields"] = "not measured this turn (CHAT)"

    # ── episodic log — gated selection ─────────────────────────────────────
    # Last 3 exchanges always shown verbatim (recency anchor).
    # Older exchanges: scored by task-overlap and keyword overlap with the
    # current observation, admitted greedily up to the mode's cap. The count of
    # omitted entries is always shown — a silent truncation reads as
    # completeness when it is not.
    if budget["episodic_chars"]:
        try:
            block, left_out = _episodic(config, agent, surface, query,
                                        budget["episodic_chars"])
            add("episodic", block)
            if left_out:
                omitted["episodes"] = left_out
        except Exception:
            pass

    if not sections:
        return ""

    # Enforce the TOTAL, after the sections have each honoured their own cap.
    sections, trimmed = _fit_total(sections, picked)
    if trimmed:
        omitted["trimmed_for_total"] = trimmed

    ctx = ("[sarsi-worker workspace]\n"
           + "\n\n".join(t for _, t in sections) + "\n[/workspace]\n\n")
    _save_context_snapshot(agent, ctx, observation=observation, mode=picked,
                           route=route, sections=sections, omitted=omitted,
                           selected=selected, budget=budget, surface=surface)
    return ctx


def _not_selected(config: Config, agent: Agent, chosen) -> list:
    """Active memory ids this turn did NOT take, capped and counted."""
    try:
        from ai4science.harness.agents.sarsi import semantic as _sem
        taken = {c for c in (chosen or []) if c}
        ids = [e.get("memory_id", "") for e in _sem.active_entries(config, agent)]
        rest = [i for i in ids if i and i not in taken]
    except Exception:
        return []
    if len(rest) > 40:
        return rest[:40] + [f"… and {len(rest) - 40} more not listed"]
    return rest


def _fit_total(sections: list, mode: str):
    """Bring the assembled context inside the mode's total. Returns
    `(sections, trimmed)` where `trimmed` names what went and by how much.

    Nothing is dropped silently: a section that is cut is *named* with the
    bytes it lost, and a section removed entirely is named too. That is the
    whole difference between a budget and a truncation. [§0.1.7, §7.2]

    Trimming takes the LARGEST eligible section each pass rather than walking a
    fixed order once: a single ordered pass removed a 16-byte board to save
    four tokens and then had nothing left to give, finishing over budget while
    reporting that it had trimmed. Sections below a floor are left alone —
    deleting a one-line section buys nothing and costs the reader a fact.
    """
    from ai4science.harness.agents.sarsi import discourse as _disc
    limits = CONTEXT_BUDGET.get(mode, CONTEXT_BUDGET["ACTION"])
    room = max(1, limits["total_tokens"] - limits["output_reserve"])
    by_name = {n: t for n, t in sections}
    trimmed: dict = {}
    #: The wrapper the caller adds around these sections counts too.
    overhead = _disc.estimate_tokens("[sarsi-worker workspace]\n\n[/workspace]\n\n")
    floor = 200

    def total() -> int:
        return overhead + _disc.estimate_tokens("\n\n".join(by_name.values()))

    for _ in range(len(TRIM_ORDER) * 4):
        over = total() - room
        if over <= 0:
            break
        eligible = [(len(by_name[n]), n) for n in TRIM_ORDER
                    if n in by_name and len(by_name[n]) > floor]
        if not eligible:
            eligible = [(len(by_name[n]), n) for n in TRIM_ORDER if n in by_name]
            if not eligible:
                break
        _, name = max(eligible)
        text = by_name[name]
        cut = min(len(text), max(400, int(over * 4.5)))
        if name in _TRIM_FROM_THE_FRONT:
            # A conversation is rendered oldest-first, so cutting the tail
            # removes the turns the reader most needs — and `why?` then points
            # at nothing. What falls out of a recent window is the OLD end;
            # that is what makes it a recent window.
            kept = text[cut:]
            head = text.splitlines()[0] if text else ""
            gone = len(text) - len(kept)
            by_name[name] = (head + f"\n  … [{gone} bytes of older {name} trimmed "
                             f"to stay inside the {mode} context budget]\n" + kept)
            trimmed[name] = f"trimmed {gone} bytes of the oldest"
            continue
        kept = text[: max(0, len(text) - cut)]
        gone = len(text) - len(kept)
        if len(kept) < floor:
            by_name.pop(name)
            trimmed[name] = f"removed ({len(text)} bytes)"
        else:
            note = (f"\n  … [{gone} bytes of {name} trimmed to stay inside the "
                    f"{mode} context budget]")
            by_name[name] = kept + note
            trimmed[name] = f"trimmed {gone} bytes"
    return [(n, by_name[n]) for n, _ in sections if n in by_name], trimmed


def _standing_id(config: Config, agent: Agent, surface: str) -> str:
    try:
        from ai4science.harness.agents.sarsi import entry as _entry
        return _entry.current(config, agent, surface=surface) or ""
    except Exception:
        return ""


def _episodic(config: Config, agent: Agent, surface: str, observation: str,
              cap: int):
    """The scored slice of older exchanges, plus how many were left out."""
    from ai4science.harness.agents.sarsi import log as _log
    log_path = _log._path(agent.agent_dir, surface)
    all_entries = _log.read(agent.agent_dir, surface, limit=0)
    total = len(all_entries)

    recent = all_entries[-3:] if len(all_entries) >= 3 else all_entries
    older = all_entries[:-3] if len(all_entries) > 3 else []

    obs_words = set((observation or "").lower().split()) - {
        "the", "a", "an", "is", "in", "to", "and", "of", "for", "it"}
    standing_id = _standing_id(config, agent, surface)

    def _score(e: dict) -> int:
        s = 0
        if standing_id and e.get("task_id") == standing_id:
            s += 2
        if obs_words:
            text = ((e.get("in") or "") + " " + (e.get("out") or "")).lower()
            s += min(2, sum(1 for w in obs_words if w in text))
        return s

    scored = sorted(older, key=_score, reverse=True)

    def _fmt(e: dict) -> str:
        ts = str(e.get("at", ""))[:16]
        inp = str(e.get("in", "")).strip()
        out = str(e.get("out", "")).strip()
        tid = f" [{e['task_id']}]" if e.get("task_id") else ""
        return f"  [{ts}]{tid} you: {inp}\n           worker: {out}"

    # The scored slice gets its own room. Seeding `chars_used` with the
    # unconditional last-3 anchor meant that once three chatty recent
    # exchanges exceeded the cap, NOTHING scored could ever be admitted — so a
    # same-task, keyword-matching older episode was crowded out by three
    # irrelevant recent ones, which is precisely the failure §11.3(c) names.
    # The anchor is still always shown; it just no longer spends the budget
    # that exists to find what is relevant.
    anchor_chars = sum(len(_fmt(e)) for e in recent)
    room = max(cap // 2, cap - anchor_chars)
    admitted: list = []
    chars_used = 0
    for e in scored:
        fmt = _fmt(e)
        if chars_used + len(fmt) > room:
            break
        admitted.append(e)
        chars_used += len(fmt)

    shown_count = len(recent) + len(admitted)
    omitted = total - shown_count
    header = (f"conversation history ({total} total, {shown_count} shown"
              + (f", {omitted} omitted — full log: {log_path}" if omitted else "")
              + "):")
    log_lines = [header]
    for e in sorted(admitted, key=lambda x: x.get("at", "")):
        log_lines.append(_fmt(e))
    if admitted and recent:
        log_lines.append("  … [gap] …")
    for e in recent:
        log_lines.append(_fmt(e))
    if not all_entries:
        log_lines.append("  (no exchanges recorded yet)")
    if not omitted:
        log_lines.append(f"  full log: {log_path}")
    return "\n".join(log_lines), max(0, omitted)


def _save_context_snapshot(agent: "Agent", ctx: str, observation: str = "", *,
                           mode: str = "ACTION", route: Any = None,
                           sections: Optional[list] = None,
                           omitted: Optional[dict] = None,
                           selected: Optional[dict] = None,
                           budget: Optional[dict] = None,
                           surface: str = "cli") -> None:
    """Persist exact `W_t` bytes + the manifest row that explains them. [§7.4]

    Files written:
      <agent_dir>/contexts/<context_id>.txt.gz  — exact context bytes
      <agent_dir>/context_manifest.jsonl        — one record per turn

    A hash alone cannot reconstruct what the model saw once the source files
    move on, so the exact rendered snapshot is stored beside the manifest, and
    the manifest carries what the snapshot cannot: which ids were selected,
    which candidates were left out and why, the budget in force, and — since
    v3 — the MODE and the router version that chose it. Without those last two
    a bad answer cannot be attributed: a routing mistake and a retrieval
    mistake look identical in the bytes.

    Never raises — context assembly must not be blocked by snapshot failures.
    """
    import gzip
    import hashlib
    import json
    import uuid
    from datetime import datetime, timezone
    try:
        from ai4science.harness.agents.sarsi import discourse as _disc
        ctx_bytes = ctx.encode("utf-8")
        context_id = f"ctx_{uuid.uuid4().hex[:12]}"
        ctx_hash = hashlib.sha256(ctx_bytes).hexdigest()
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        ctx_dir = agent.agent_dir / "contexts"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        gz_path = ctx_dir / f"{context_id}.txt.gz"
        with gzip.open(gz_path, "wb") as fh:
            fh.write(ctx_bytes)

        manifest_path = agent.agent_dir / "context_manifest.jsonl"
        record = {
            "schema_version": 2,
            "context_id": context_id,
            "at": ts,
            "surface": surface,
            "sha256": ctx_hash,
            "byte_count": len(ctx_bytes),
            "gz_path": str(gz_path),
            "query_snippet": (observation or "")[:80],
            "mode": mode,
            "gate_version": GATE_VERSION,
            "router_version": getattr(route, "router_version", ""),
            "route": route.as_record() if hasattr(route, "as_record") else {},
            "budget": dict(budget or {}),
            "token_estimate": _disc.estimate_tokens(ctx),
            "token_estimator": _disc.estimator(),
            # Per-section content hashes, not just the whole-context one:
            # §7.4 asks for "selected content hashes", and a single hash over
            # the concatenation cannot tell a reader WHICH part changed
            # between two otherwise similar turns.
            "sections": [{"name": n,
                          "bytes": len(t.encode("utf-8")),
                          "sha256": hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]}
                         for n, t in (sections or [])],
            "selected": dict(selected or {}),
            "omitted": dict(omitted or {}),
        }
        with manifest_path.open("a") as mf:
            mf.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except Exception:
        pass


def manifest(agent_dir: "Path", limit: int = 0) -> List[Dict[str, Any]]:
    """The context manifest, oldest-first. Rows that predate a schema version
    are returned as they were written — history is read, not rewritten."""
    import json
    p = agent_dir / "context_manifest.jsonl"
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for ln in p.read_text().splitlines():
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows if not limit else rows[-limit:]


def replay(agent_dir: "Path", context_id: str) -> Optional[str]:
    """The exact bytes a past turn saw, or None. [§7.4]

    Read from the stored snapshot and checked against the hash the manifest
    recorded at the time. A context hash plus section counts cannot rebuild an
    input once the source files move on — which is the whole reason the bytes
    are kept rather than described. A mismatch returns None: a snapshot that
    does not match its own manifest is not evidence of anything.
    """
    import gzip
    import hashlib
    for row in manifest(agent_dir):
        if row.get("context_id") != context_id:
            continue
        gz = row.get("gz_path") or ""
        try:
            raw = gzip.open(gz, "rb").read()
        except Exception:
            return None
        want = row.get("sha256") or ""
        if want and hashlib.sha256(raw).hexdigest() != want:
            return None
        return raw.decode("utf-8")
    return None


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
