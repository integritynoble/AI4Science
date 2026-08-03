"""What actually carries an approved act out of the machine.

The gate was built first and deliberately had nothing behind it. This is the
behind, and it is the most dangerous code here, because it is the only part that
reaches a person.

Four rules:

  * **there is no default transmitter.** A kind nobody wired raises
    `NoTransmitter` and names it. It never falls back to something that looks
    close — "close" here means a message to the wrong person.
  * **`pay` can never have one.** No grant authorises a payment at any tier, so
    a transmitter for it would be a way around a rule the rest of the design
    takes seriously. Registering one raises.
  * **credentials come from the vault, at send time, for that one act.** Never
    from config, never held on the transmitter between acts — a transmitter that
    cached the password would have turned one approval into standing access.
  * **it reports what it actually sent**, so `OWN`'s approved-bytes check has
    something real to compare against.

The recipient and the subject are transmitted too, so they are part of the
act's digest and are shown to the owner. An approval of a body whose subject
nobody read is an approval of half the message.
"""
from __future__ import annotations

from email.message import EmailMessage
from typing import Any, Callable, Dict, Optional

from ai4science.harness.agents.sarsi import outward, vault
from ai4science.harness.agents.sarsi.registry import Agent, Config


class NoTransmitter(Exception):
    """Nothing is wired to carry this kind of act."""


class TransmitFailed(Exception):
    """The send did not happen. Never reported as a success."""


_REGISTRY: Dict[str, Callable[..., str]] = {}


def register(kind: str, transmitter: Callable[..., str]) -> None:
    if kind in outward.MONEY:
        raise outward.Reserved(
            f"{kind} moves money: no grant authorises it at any tier, so it may "
            f"not have a transmitter either")
    _REGISTRY[kind] = transmitter


def unregister(kind: str) -> None:
    _REGISTRY.pop(kind, None)


def for_act(config: Config, agent: Agent, act: outward.Act) -> Callable[..., str]:
    transmitter = _REGISTRY.get(act.kind)
    if transmitter is None:
        raise NoTransmitter(
            f"nothing is wired to {act.kind} — the gate would approve this and "
            f"then have nowhere to send it")
    return transmitter


# ── mail ──────────────────────────────────────────────────────────────

def _default_smtp(*, host: str, port: int, user: str, password: str,
                  message: str, to: str) -> bool:
    import smtplib
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to], message)
    return True


def smtp_mail(config: Config, agent: Agent, *, host: str, port: int, user: str,
              secret: str, prompt: Callable[..., Any],
              smtp: Callable[..., bool] = _default_smtp) -> Callable[..., str]:
    """A transmitter for `mail`, credentialled through the vault per send."""

    def send(act: outward.Act, *, body: str) -> str:
        # asked for THIS act, at send time — not held between them
        decision = vault.ask(config, agent_id=agent.id, secret=secret,
                             act="send", purpose=f"send mail to {act.destination}",
                             prompt=prompt, outward=True,
                             standing_grants=agent.standing_grants)
        if not decision.allowed:
            raise TransmitFailed(decision.reason)

        message = EmailMessage()
        # from the act the owner saw rendered, and from nowhere else, so there
        # is nothing that could drift between approval and transmission
        message["To"] = act.destination
        message["From"] = user
        message["Subject"] = act.subject
        message.set_content(body)

        try:
            smtp(host=host, port=port, user=user, password=decision.value or "",
                 message=message.as_string(), to=act.destination)
        except Exception as e:
            raise TransmitFailed(f"the message was not sent: {e}")
        return body                 # exactly what went out, for OWN to compare

    return send


def dry_run(record: Optional[list] = None) -> Callable[..., str]:
    """Goes through the whole gate and then does not send. What `--dry-run` uses."""
    def send(act: outward.Act, *, body: str) -> str:
        if record is not None:
            record.append({"to": act.destination, "subject": act.subject,
                           "body": body})
        return body
    return send
