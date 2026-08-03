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


# ── publishing ────────────────────────────────────────────────────────

class TooLongToPost(Exception):
    """Over the platform's limit. Refused — never truncated."""


#: Where each platform takes a post, and what it will accept.
#: `limit=None` means the platform imposes none we need to enforce.
PLATFORMS: Dict[str, Dict[str, Any]] = {
    "x": {"url": "https://api.twitter.com/2/tweets", "limit": 280,
          "field": "text"},
    "linkedin": {"url": "https://api.linkedin.com/v2/ugcPosts", "limit": 3000,
                 "field": "text"},
    "substack": {"url": "https://substack.com/api/v1/posts", "limit": None,
                 "field": "text"},
}


def _default_http(*, url: str, token: str, payload: Dict[str, Any],
                  timeout: float):
    import json as _json
    import urllib.error
    import urllib.request
    request = urllib.request.Request(
        url, data=_json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read()[:200].decode("utf-8", "replace")}


def post(config: Config, agent: Agent, *, platform: str, secret: str,
         prompt: Callable[..., Any], http: Callable[..., Any] = _default_http,
         timeout: float = 30.0) -> Callable[..., str]:
    """A transmitter for `post`, one platform at a time.

    It returns **what the platform says it published**, not what we asked it to
    publish. When those differ — a trimmed line, a shortened link, a stripped
    character — `OWN`'s approved-bytes check raises. A platform that alters your
    words is caught rather than accommodated, which is the whole of the rule
    that the approved draft and the published thing must be shown identical.
    """
    spec = PLATFORMS.get(platform)
    if spec is None:
        raise NoTransmitter(
            f"no transmitter for {platform!r} — known platforms: "
            f"{', '.join(sorted(PLATFORMS))}")

    def precheck(act: outward.Act) -> None:
        """What this platform can already tell is unpublishable. Run by `OWN`
        before the owner is asked."""
        limit = spec["limit"]
        body = act.body
        if limit is not None and len(body) > limit:
            # Refused, never truncated: truncating publishes something nobody
            # approved, and removes the end — where the meaning usually lands.
            raise TooLongToPost(
                f"{len(body)} characters is {len(body) - limit} over "
                f"{platform}'s limit of {limit}. Shorten it yourself and ask "
                f"again — I will not cut it for you.")

    def send(act: outward.Act, *, body: str) -> str:
        precheck(outward.Act(agent_id=act.agent_id, kind=act.kind,
                             destination=act.destination, body=body,
                             subject=act.subject))
        decision = vault.ask(config, agent_id=agent.id, secret=secret,
                             act="post", purpose=f"post to {platform}",
                             prompt=prompt, outward=True,
                             standing_grants=agent.standing_grants)
        if not decision.allowed:
            raise TransmitFailed(decision.reason)

        try:
            status, answer = http(url=spec["url"], token=decision.value or "",
                                  payload={spec["field"]: body}, timeout=timeout)
        except Exception as e:
            raise TransmitFailed(f"the post was not published: {e}")
        if not (200 <= int(status) < 300):
            raise TransmitFailed(f"{platform} refused the post: {status} "
                                 f"{(answer or {}).get('error', '')}")

        published = (answer or {}).get(spec["field"])
        if not published:
            # Silence about what went out is not confirmation that it matched.
            raise TransmitFailed(
                f"{platform} did not confirm what it published, so there is "
                f"nothing to compare against what you approved")
        return published

    send.precheck = precheck            # so OWN can ask before it asks you
    return send


def dry_run(record: Optional[list] = None) -> Callable[..., str]:
    """Goes through the whole gate and then does not send. What `--dry-run` uses."""
    def send(act: outward.Act, *, body: str) -> str:
        if record is not None:
            record.append({"to": act.destination, "subject": act.subject,
                           "body": body})
        return body
    return send
