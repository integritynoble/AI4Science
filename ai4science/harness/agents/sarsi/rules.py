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
