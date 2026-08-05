"""The gateway — one local daemon hosting every agent, one bot per agent.

openclaw's shape: `channels.telegram.accounts.<id>.botToken` gives each agent
its own conversation, and `bindings` says which agent owns which account. The
gateway is the loop that turns those two tables into delivered messages.

Three properties it is built to keep:

  * **a stranger is dropped, counted, and never answered.** Not even a refusal
    goes back — a reply would confirm the bot exists and is listening.
  * **a dropped turn is counted, not transcribed.** An unknown sender must not
    be able to write arbitrary text into the owner's records.
  * **one failure is one failure.** A bot that errors, or an agent handler that
    raises, costs that turn and nothing else; the other agents keep running.

The Telegram transport is injected, so the rules above are testable without a
network and the daemon has exactly one place that talks to the outside world.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ai4science.harness.agents.machine import telegram as tg
from ai4science.harness.agents.sarsi import (digest, ledger, ownerlog,
                                             router)
from ai4science.harness.agents.sarsi.registry import Agent, Config

OFFSETS_NAME = "gateway-offsets.json"
TELEGRAM = "telegram"


class TelegramTransport:
    """The real one. Two calls, both stdlib, both owner-token scoped."""

    def get_updates(self, token: str, offset: Optional[int] = None, *,
                    timeout: int = 0) -> list:
        return tg.get_updates(token, offset=offset, timeout=timeout)

    def send_message(self, token: str, chat_id: str, text: str) -> dict:
        return tg.send_message(token, chat_id, text)


Handler = Callable[..., Optional[str]]


class Gateway:
    def __init__(self, config: Config, *, transport: Any = None,
                 handler: Optional[Handler] = None,
                 now: Callable[[], float] = time.time) -> None:
        self.config = config
        self.transport = transport or TelegramTransport()
        self.handler = handler or self._board
        self.now = now
        self._offsets: Dict[str, int] = _load_offsets(config)

    # ── one pass over every configured bot ────────────────────────────

    def poll_once(self) -> int:
        handled = 0
        # Unprompted digests. Almost every pass does nothing — the sweep holds
        # the once-a-period rule, and this only supplies the way to send.
        try:
            digest.sweep(self.config, send=self._deliver_digest)
        except Exception:
            pass                              # a digest must not stop the poll

        for account_id, token in _accounts(self.config).items():
            if not token:
                continue                      # no token: this agent is not on Telegram
            try:
                updates = self.transport.get_updates(token, offset=self._offsets.get(account_id))
            except Exception:
                continue                      # one bot down is not the fleet down
            for update in updates or []:
                # keyed by account id, never by token: bookkeeping must not copy
                # a credential out of the registry into a second file
                self._offsets[account_id] = int(update.get("update_id", 0)) + 1
                try:
                    handled += self._dispatch(account_id, token, update)
                except Exception:
                    continue
        _save_offsets(self.config, self._offsets)
        return handled

    def _board(self, *, agent: Agent, text: str, surface: str, chat_id: str) -> str:
        return handle(self.config, agent=agent, text=text, surface=surface,
                      chat_id=chat_id)

    def run(self, *, interval: float = 2.0, passes: Optional[int] = None,
            sleep: Callable[[float], None] = time.sleep) -> None:
        n = 0
        while passes is None or n < passes:
            self.poll_once()
            n += 1
            if passes is None or n < passes:
                sleep(interval)

    def _deliver_digest(self, agent, text: str) -> bool:
        """To the OWNER, on that agent's own bot. Returns whether it landed.

        An agent with no token has nowhere to send, and that returns False
        rather than True: marking it delivered would lose the content, because
        the next digest begins where this one ended.
        """
        token = (_accounts(self.config).get(agent.id) or "").strip()
        if not token:
            return False
        try:
            answer = self.transport.send_message(token, self.config.owner_id,
                                                 text)
        except Exception:
            return False
        return bool((answer or {}).get("ok", True))

    # ── one update ────────────────────────────────────────────────────

    def _dispatch(self, account_id: str, token: str, update: Dict[str, Any]) -> int:
        message = update.get("message")
        if not isinstance(message, dict):
            return 0                          # edits, joins, callbacks: not ours here
        text = message.get("text")
        chat_id = str((message.get("chat") or {}).get("id") or "")
        sender_id = (message.get("from") or {}).get("id")

        decision = router.decide(self.config, channel=TELEGRAM,
                                 account_id=account_id,
                                 sender_id=None if sender_id is None else str(sender_id))
        if decision.dropped:
            # counted, never transcribed, never answered
            ledger.append(self.config, "inbound",
                          {"channel": TELEGRAM, "account": account_id,
                           "accepted": False, "reason": decision.reason},
                          now=self.now)
            return 0

        agent = decision.agent
        ledger.append(self.config, "inbound",
                      {"channel": TELEGRAM, "account": account_id,
                       "agent": agent.id, "accepted": True, "chars": len(text or "")},
                      now=self.now)
        # one log per agent, both doors — so the CLI sees this and does not re-ask it
        ownerlog.append(self.config, agent, text or "", surface=TELEGRAM, now=self.now)
        try:
            reply = self.handler(agent=agent, text=text or "", surface=TELEGRAM,
                                 chat_id=chat_id)
        except Exception as e:
            # The owner asked and is owed an answer; say what happened rather
            # than leaving the message unanswered.
            reply = f"{agent.id} could not answer: {type(e).__name__}"
        if reply:
            # Logged before the send, and logged whatever the handler returned:
            # the record is what the agent answered, not what the transport
            # managed to deliver. A reply that failed to send is still the
            # thing the owner is owed, and scroll-back should show it.
            ownerlog.reply(self.config, agent, reply, surface=TELEGRAM, now=self.now)
            try:
                self.transport.send_message(token, chat_id, reply)
            except Exception:
                pass
        return 1


def handle(config: Config, *, agent: Agent, text: str, surface: str,
           chat_id: str = "") -> str:
    """The default handler for both doors: the board.

    Kept here so the Telegram loop and the CLI reach the same code — an agent
    has one set of tasks regardless of which surface asked about them.
    """
    from ai4science.harness.agents.sarsi import chat
    return chat.handle(config, agent, text, surface=surface)


# ── accounts and offsets ──────────────────────────────────────────────

def _accounts(config: Config) -> Dict[str, str]:
    if not config.path or not Path(config.path).exists():
        return {}
    raw = json.loads(Path(config.path).read_text())
    accounts = ((raw.get("channels") or {}).get(TELEGRAM) or {}).get("accounts") or {}
    return {aid: (spec or {}).get("botToken") or "" for aid, spec in accounts.items()}


def _offsets_path(config: Config) -> Path:
    return config.root / OFFSETS_NAME


def _load_offsets(config: Config) -> Dict[str, int]:
    path = _offsets_path(config)
    if not path.exists():
        return {}
    try:
        return {str(k): int(v) for k, v in json.loads(path.read_text()).items()}
    except Exception:
        return {}


def _save_offsets(config: Config, offsets: Dict[str, int]) -> None:
    path = _offsets_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(offsets, sort_keys=True))
    try:
        path.chmod(0o600)
    except Exception:
        pass
