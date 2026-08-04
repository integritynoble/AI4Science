"""The workspace a node is given — the history it plans and steers from.

A node with no workspace starts every time from nothing, which is how an agent
re-learns the same thing weekly and asks again for a permission it was already
told about. This is where `W_name` earns its keep, and the planning node is
where it matters most: a plan written without the history repeats every mistake
the history records.

**Built from records, never summarised by a model.** A model-written précis of
what happened is narration standing in for history — it reads like evidence and
is not. Every line below is *promoted* from something already written down: the
owner log, the grants on the task, the ledgers, the plans that earned a pass.

Three rules:

  * **bounded, with the overflow counted.** "…and 14 more" is information; a
    quiet truncation is a claim of completeness that is false.
  * **no secret value, ever.** Which secret was asked for may travel — the owner
    cannot grant one they cannot name — but never what it is.
  * **no host-local fact travels.** Tools, paths and resource readings are about
    *this* machine and mean nothing off it. Copying them upward is how a fleet
    convinces itself it can do something it cannot.
"""
from __future__ import annotations

from typing import List

from ai4science.harness.agents.sarsi import ledger, ownerlog, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

MAX_CHARS = 6000
KEEP_SAID = 8
KEEP_PRECEDENT = 5
KEEP_MISSES = 5
#: How many RECURRING lines the fold may promote out of the overflow. Bounded,
#: or a history that repeats itself becomes a second full history.
KEEP_FOLDED = 3
#: A line has to appear at least this often to be worth promoting past newer
#: ones. Twice is coincidence; three times is the owner insisting.
FOLD_AT = 3


def render(config: Config, agent: Agent, task: tsk.Task) -> str:
    """What this agent already knows that bears on this task."""
    blocks: List[str] = []

    # W_shared, when the owner granted it. Read at PLAN time, never pushed: an
    # agent that is not planning does not read, and a fact published today is
    # found by whoever plans tomorrow.
    from ai4science.harness.agents.sarsi import shared as _shared
    published = _shared.render(config, agent)
    if published:
        blocks.append(published)

    said = ownerlog.said(config, agent, limit=0)
    if said:
        blocks.append(_block(
            "WHAT YOU HAVE BEEN TOLD (the owner's own words, authoritative for "
            "what they want)",
            [e.get("text", "") for e in said], KEEP_SAID))

    if task.grants:
        blocks.append(_block("ALREADY GRANTED FOR THIS TASK", list(task.grants),
                             KEEP_SAID))

    precedent = _precedent(config, agent, task)
    if precedent:
        blocks.append(_block(
            "CRITERIA THAT PASSED BEFORE (a shape worth reusing)",
            precedent, KEEP_PRECEDENT))

    misses = _planning_misses(config, agent)
    if misses:
        blocks.append(_block(
            "PERMISSIONS DISCOVERED MID-RUN BEFORE — declare these up front if "
            "this task needs them",
            misses, KEEP_MISSES))

    denied = _vault_denials(config, agent)
    if denied:
        blocks.append(_block(
            "SECRETS THAT WERE REFUSED BEFORE (named, never their values)",
            denied, KEEP_MISSES))

    if not blocks:
        return "HISTORY: nothing recorded for this agent yet."

    text = "\n\n".join(blocks)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n… [more, not shown]"
    return text


def _block(title: str, items: List[str], keep: int) -> str:
    """The most recent `keep`, plus a **fold** of what recurs in the overflow.

    A tail keeps what is newest. What it silently loses is the thing said five
    times and then not again — usually the thing that matters most, because
    repetition is how an owner insists.

    The fold is a **tally, not a précis**: every promoted line is a line that
    was actually written, with the number of times it was written. This module
    does not let a model summarise its history, and a fold that paraphrased
    would be exactly that with a different name.
    """
    # The visible window is the scarce thing, so a repeated line takes ONE
    # slot and carries its count. Live, four identical gate notices filled a
    # whole block while distinct history sat unshown.
    total: dict = {}
    for item in items:
        if item:
            total[item] = total.get(item, 0) + 1

    shown: List[str] = []
    taken = set()
    for item in reversed(items):
        if not item or item in taken:
            continue
        taken.add(item)
        shown.append(item)
        if len(shown) >= keep:
            break
    shown.reverse()

    overflow = [i for i in items if i and i not in taken]

    counts: dict = {}
    for item in overflow:
        counts[item] = counts.get(item, 0) + 1
    # recurrence, not age: promoting everything old would make the fold a
    # second full history
    folded = [(item, n) for item, n in counts.items()
              if n >= FOLD_AT and item not in shown]
    folded.sort(key=lambda pair: (-pair[1], pair[0]))
    folded = folded[:KEEP_FOLDED]

    lines = [f"{title}:"]
    for item in shown:
        n = total.get(item, 1)
        lines.append(f"  - {item}" + (f"  ×{n}" if n > 1 else ""))
    for item, n in folded:
        lines.append(f"  - {item}  ×{n}")

    promoted = sum(n for _, n in folded)
    seen_in_shown = sum(total.get(i, 1) for i in shown)
    hidden = len(items) - seen_in_shown - promoted
    if hidden > 0:
        # still counted after promotion: the fold changes what is SHOWN, never
        # whether the rest is admitted to
        lines.append(f"  … and {hidden} more, not shown")
    return "\n".join(lines)


def _precedent(config: Config, agent: Agent, task: tsk.Task) -> List[str]:
    out: List[str] = []
    for other in tsk.all_of(config, agent):
        if other.id == task.id or other.state != tsk.VERIFIED:
            continue
        if (other.verdict or {}).get("state") != "PASS":
            continue
        out.extend(other.criteria or [])
    return out


def _planning_misses(config: Config, agent: Agent) -> List[str]:
    """Gates that were met mid-run. A plan that declared its permissions should
    not meet one, so each is a lesson for the next plan."""
    out: List[str] = []
    for row in ledger.read(config, "reports"):
        if row.get("agent") != agent.id or row.get("state") != "gate":
            continue
        for e in row.get("evidence") or []:
            out.append(str(e))
    return out


def _vault_denials(config: Config, agent: Agent) -> List[str]:
    out: List[str] = []
    for row in ledger.read(config, "vault"):
        if row.get("agent") != agent.id or row.get("decision") != "DENY":
            continue
        name = row.get("secret")
        if name and name not in out:
            out.append(str(name))
    return out
