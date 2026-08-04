"""`RUL` — the host facts every session would otherwise rediscover.

A live session ran `python demo.py`, met `/bin/sh: 1: python: not found`, and
retried with `python3`. Cheap once, and paid again by every session that starts
on this machine. *"Use python3 on this host"* is a fact about the host, and it
belongs somewhere a session is **told** rather than somewhere it has to bump
into.

Where they live matters as much as what they say. They sit in **`W_host`**, the
per-agent host workspace, because a host-local fact never travels: a path that
exists here means nothing on another machine, and promoting one upward is how a
fleet convinces itself it can do something it cannot.

Three rules:

  * **the owner writes them.** An agent that can write its own standing
    instructions can widen its own instructions, and that is the single thing
    the permission design exists to prevent. An agent may learn that `python3`
    is the right binary; turning that into a standing instruction is the
    owner's act.
  * **bounded.** A rules file that grows forever becomes a second prompt nobody
    reads, and an unread rule is worse than an absent one — it looks like
    coverage.
  * **no secret value.** A rule may *name* a credential so a session knows to
    ask for it. It may not carry one.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from ai4science.harness.agents.sarsi.registry import Agent, Config

FILE_NAME = "HOUSE_RULES.md"
#: Held beside the rules, never inside them: a proposal is not a rule, and a
#: session must not be able to read one as though it were.
PENDING_NAME = "HOUSE_RULES.pending.json"
#: Small on purpose. Past this the file stops being read, and a rule nobody
#: reads is worse than no rule: it looks like coverage.
MAX_RULES = 12
MAX_CHARS = 300

#: A rule that looks like it is carrying a value rather than naming one.
_SECRET = re.compile(
    r"\b(password|passphrase|api[- ]?key|token|secret|credential)\b"
    r"\s*(is|=|:)\s*\S", re.I)


class TooMany(Exception):
    """The file is full. Something has to go before something is added."""


class LooksLikeASecret(Exception):
    """It reads as a value, not a name. Values live in the vault."""


class NoSuchRule(Exception):
    """Nothing here matches what was asked to be removed."""


class OwnerMustSign(Exception):
    """An agent cannot adopt its own standing instruction."""


def path(agent: Agent) -> Path:
    return agent.host / FILE_NAME


def read(config: Config, agent: Agent) -> List[str]:
    """The rules, in the order they were written."""
    try:
        text = path(agent).read_text()
    except OSError:
        return []
    out: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- "):
            out.append(line[2:].strip())
    return [r for r in out if r]


def add(config: Config, agent: Agent, rule: str) -> List[str]:
    text = (rule or "").strip()
    if not text:
        raise ValueError("a rule with nothing in it is not a rule")
    if len(text) > MAX_CHARS:
        raise ValueError(
            f"{len(text)} characters is past the {MAX_CHARS} a rule may be — a "
            f"rule that needs a paragraph is a plan, and belongs in one")
    if _SECRET.search(text):
        raise LooksLikeASecret(
            "that reads as a secret VALUE, not the name of one. Put the value "
            "in the vault and let the rule name it — this file is not a place "
            "for a second copy of a credential")

    current = read(config, agent)
    if text in current:
        return current                # said twice, kept once
    if len(current) >= MAX_RULES:
        raise TooMany(
            f"{agent.id} already has {MAX_RULES} house rules, which is as many "
            f"as a session will actually read. Remove one first: "
            f"`sarsi rules {agent.id} --remove \"<the rule>\"`")

    current.append(text)
    _write(agent, current)
    return current


def remove(config: Config, agent: Agent, rule: str) -> List[str]:
    current = read(config, agent)
    text = (rule or "").strip()
    if text not in current:
        raise NoSuchRule(f"{agent.id} has no rule {text[:60]!r}")
    current = [r for r in current if r != text]
    _write(agent, current)
    return current


def render(config: Config, agent: Agent) -> str:
    """What a kickoff says about them, or "" when there are none."""
    current = read(config, agent)
    if not current:
        return ""
    lines = ["House rules for this machine — the owner's standing "
             "instructions, and they outrank your own guess about this host:"]
    lines += [f"  - {r}" for r in current]
    return "\n".join(lines)


# ── an agent may propose one, and only propose ────────────────────────

def _pending_path(agent: Agent) -> Path:
    return agent.host / PENDING_NAME


def pending(config: Config, agent: Agent):
    """The proposal waiting on the owner, or None."""
    import json
    try:
        raw = json.loads(_pending_path(agent).read_text())
    except Exception:
        return None
    return raw if raw.get("rule") else None


def propose(config: Config, agent: Agent, rule: str, *, because: str) -> dict:
    """An agent asks for a standing instruction. It does not get one.

    The motivating case is an agent LEARNING that `python3` is the binary here.
    Learning it is the agent's; making it standing is the owner's — an agent
    that could adopt its own standing instructions could widen its own
    instructions, which is the single thing this design exists to prevent.

    Held to every standard `add` holds, so a proposal cannot be a way around
    them, and **one at a time**: a queue of proposals is a queue of decisions,
    and the owner is being asked one question.
    """
    import json

    text = (rule or "").strip()
    reason = (because or "").strip()
    if not text:
        raise ValueError("a rule with nothing in it is not a rule")
    if not reason:
        # The owner is being asked to make something standing; "it proposed a
        # rule" is not enough to decide on.
        raise ValueError(
            "a proposal has to say what happened that makes it worth a "
            "standing rule — the owner is deciding, not rubber-stamping")
    if _SECRET.search(text):
        raise LooksLikeASecret(
            "that reads as a secret VALUE, not the name of one — the vault "
            "holds values, and a proposal is not a way around that")
    if text in read(config, agent):
        raise ValueError(f"{agent.id} already follows that rule")

    record = {"rule": text, "because": reason[:MAX_CHARS]}
    path = _pending_path(agent)
    agent.host.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return record


def sign(config: Config, agent: Agent, *, by_owner: bool):
    """Adopt the pending proposal. Only the owner may."""
    if not by_owner:
        raise OwnerMustSign(
            f"{agent.id} cannot sign its own proposal; the only path from a "
            f"proposal to a standing rule is the owner's signature")
    proposal = pending(config, agent)
    if proposal is None:
        return None                   # a signature with nothing pending is a
                                      # no-op, not an accident
    # `add` still applies: if the file is full the proposal STAYS pending
    # rather than being dropped on the floor.
    add(config, agent, proposal["rule"])
    discard(config, agent)
    return proposal


def discard(config: Config, agent: Agent) -> None:
    try:
        _pending_path(agent).unlink()
    except OSError:
        pass


def _write(agent: Agent, current: List[str]) -> None:
    agent.host.mkdir(parents=True, exist_ok=True)
    body = ["# House rules", "",
            f"Host facts for `{agent.id}` on this machine. They do not travel: "
            f"a path that exists here means nothing elsewhere.", ""]
    body += [f"- {r}" for r in current]
    target = path(agent)
    target.write_text("\n".join(body) + "\n")
    try:
        target.chmod(0o600)
    except OSError:
        pass
