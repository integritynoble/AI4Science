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
    lines.append("I do not execute anything myself. I open a task, agree a plan "
                 "with you, and a session does the work — sarsi-claude runs "
                 "Anthropic's claude binary, sarsi-pwm runs ai4science.")
    return "\n".join(lines)


#: Words that make a question about THIS AGENT rather than about the world.
#: Deliberately narrow: a router that guesses is worse than one that is quiet,
#: and a question this cannot answer from its own state must reach the model
#: rather than a canned page.
_SELF = ("you", "your", "yours", "yourself", "i am", "am i")
_ABOUT = ("ceiling", "a0", "a1", "a2", "a3", "permission", "grant", "task",
          "tasks", "plan", "backend", "tool", "tools", "who", "what", "which",
          "can", "may", "able", "holding", "doing", "role", "agent")


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
