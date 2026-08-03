"""One decision per inbound turn: may this speaker be heard, and by whom.

Kept pure — no I/O, no network, no clock — so the two rules it enforces can be
tested exactly as they are written:

  * **the owner lock is checked on every turn**, not once at pairing. A message
    from any other id is dropped and counted, never answered.
  * **an unmatched account resolves to nothing.** There is no default agent, so
    a missing binding can never deliver a personal message to the work agent.

The CLI is a different kind of door: it carries no channel identity, and is
trusted to the OS user who owns the state root. That is why `sender_id` is
required for Telegram and irrelevant for the CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

CLI_CHANNEL = "cli"


@dataclass(frozen=True)
class Decision:
    accepted: bool
    agent_id: Optional[str] = None
    agent: Optional[Agent] = None
    reason: Optional[str] = None      # "not-owner" | "no-binding" | None

    @property
    def dropped(self) -> bool:
        return not self.accepted


def _drop(reason: str) -> Decision:
    # No agent record travels with a refusal: nothing downstream may act on it.
    return Decision(accepted=False, reason=reason)


def decide(config: Config, *, channel: str, account_id: str,
           sender_id: Optional[str] = None) -> Decision:
    if channel != CLI_CHANNEL and not is_owner(config, sender_id):
        return _drop("not-owner")
    agent_id = config.resolve(channel, account_id)
    if agent_id is None:
        return _drop("no-binding")
    return Decision(accepted=True, agent_id=agent_id, agent=config.agents[agent_id])


def is_owner(config: Config, sender_id: Optional[str]) -> bool:
    """Exact match on the whole id. A prefix is a different account."""
    if sender_id is None:
        return False
    return str(sender_id).strip() == config.owner_id
