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

from dataclasses import dataclass
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
    # `id_field` is what the platform calls the thing it just published. It is
    # kept so a post can be identified later — without it `undo` cannot say
    # WHICH post to take back, and deleting the wrong one is worse than none.
    # `delete_url` is how a published post is taken down, `{handle}` standing
    # for the id the platform returned. `None` means the platform offers no
    # deletion — stated, so `undo` refuses by name instead of attempting.
    "x": {"url": "https://api.twitter.com/2/tweets", "limit": 280,
          "field": "text", "id_field": "id",
          "delete_url": "https://api.twitter.com/2/tweets/{handle}"},
    "linkedin": {"url": "https://api.linkedin.com/v2/ugcPosts", "limit": 3000,
                 "field": "text", "id_field": "id",
                 "delete_url": "https://api.linkedin.com/v2/ugcPosts/{handle}"},
    "substack": {"url": "https://substack.com/api/v1/posts", "limit": None,
                 "field": "text", "id_field": "id",
                 "delete_url": "https://substack.com/api/v1/posts/{handle}"},
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

        # What the platform called it, for `undo`. Absent is absent: a blank
        # handle is what stops a retraction from guessing.
        send.handle = str((answer or {}).get(spec.get("id_field") or "id") or "")

        published = (answer or {}).get(spec["field"])
        if not published:
            # Silence about what went out is not confirmation that it matched.
            raise TransmitFailed(
                f"{platform} did not confirm what it published, so there is "
                f"nothing to compare against what you approved")
        return published

    send.precheck = precheck            # so OWN can ask before it asks you
    send.handle = ""                    # set per publish; see `outward._transmit`
    return send


def _default_delete(*, url: str, token: str, timeout: float):
    import json as _json
    import urllib.error
    import urllib.request
    request = urllib.request.Request(
        url, method="DELETE",
        headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read()[:200].decode("utf-8", "replace")}


def retractor(config: Config, agent: Agent, *, platform: str, secret: str,
              prompt: Callable[..., Any], http: Callable[..., Any] = _default_delete,
              timeout: float = 30.0) -> Callable[..., str]:
    """Take a published post down. Shaped entirely by one asymmetry:

    **failing to delete leaves a post up, which the owner can see and retry;
    deleting the wrong thing cannot be undone at all.** So every ambiguity here
    resolves toward doing nothing.
    """
    spec = PLATFORMS.get(platform)
    if spec is None:
        raise NoTransmitter(
            f"no transmitter for {platform!r} — known platforms: "
            f"{', '.join(sorted(PLATFORMS))}")
    if not spec.get("delete_url"):
        raise NoTransmitter(
            f"{platform!r} offers no way to delete a post, so nothing here can "
            f"take one down. Remove it yourself.")

    def pull(act) -> str:
        handle = str(getattr(act, "handle", "") or "")
        if not handle:
            # Checked before the secret is even asked for: without an id there
            # is nothing to delete, and a guess would delete someone else's.
            raise TransmitFailed(
                "no handle was recorded for this post, so there is nothing to "
                "identify which one to take down")

        decision = vault.ask(config, agent_id=agent.id, secret=secret,
                             act="retract", purpose=f"delete a post on {platform}",
                             prompt=prompt, outward=True,
                             standing_grants=agent.standing_grants)
        if not decision.allowed:
            raise TransmitFailed(decision.reason)

        url = str(spec["delete_url"]).format(handle=handle)
        try:
            status, answer = http(url=url, token=decision.value or "",
                                  timeout=timeout)
        except Exception as e:
            raise TransmitFailed(f"the post is still published: {e}")

        status = int(status)
        if status == 404:
            # "Already gone" and "wrong id" are indistinguishable from here, and
            # one of them means this deleted nothing while reporting that it did.
            raise TransmitFailed(
                f"{platform} answered 404 for post {handle}: either it is "
                f"already gone or that is not its id. Nothing was deleted, and "
                f"this will not claim otherwise — check it yourself.")
        if not (200 <= status < 300):
            raise TransmitFailed(
                f"{platform} refused to delete post {handle}: {status} "
                f"{(answer or {}).get('error', '')} — it is still published")
        return handle

    return pull


# ── submitting an application ─────────────────────────────────────────

class AskTheOwnerFirst(Exception):
    """A form carried an owner fact nobody stated. It asks rather than invents."""


class IncompleteForm(Exception):
    """A required field was empty. A half-submitted application cannot be
    taken back and completed."""


@dataclass(frozen=True)
class Field:
    name: str
    value: str
    required: bool = False
    #: True only when the OWNER stated this, not when the agent worked it out.
    supplied: bool = False


@dataclass(frozen=True)
class Form:
    url: str
    fields: tuple = ()

    def render(self) -> str:
        """Every field and value, one per line.

        A form is what goes out, so a form is what the owner is shown. A prose
        summary of an application is not the application.
        """
        return "\n".join(f"{f.name}: {f.value}" for f in self.fields)

    def values(self) -> Dict[str, str]:
        return {f.name: f.value for f in self.fields}


def submission(agent: Agent, form: Form) -> outward.Act:
    """The act for a form: its body IS the form, and it declares itself one-way."""
    return outward.Act(agent_id=agent.id, kind="submit", destination=form.url,
                       body=form.render(),
                       reversibility={"irreversible": True})


def submit_form(config: Config, agent: Agent, form: Form, *,
                driver: Callable[..., Dict[str, str]],
                timeout: float = 120.0) -> Callable[..., str]:
    """A transmitter for `submit`, built for **one** form.

    Taking the form here rather than binding it afterwards is deliberate: a
    transmitter holding a form set somewhere else could be handed an act built
    from a different one, and the thing submitted would not be the thing
    approved.

    The driver returns **what it actually entered**, so a site that trims,
    re-cases, auto-completes or silently drops a field is caught by `OWN` rather
    than discovered weeks later in a rejection.
    """

    def precheck(act: outward.Act) -> None:
        from ai4science.harness.agents.sarsi import specs
        if act.body != form.render():
            raise IncompleteForm(
                "this act was not built from the form this transmitter holds")
        for field in form.fields:
            if field.name in specs.OWNER_FACTS and not field.supplied:
                raise AskTheOwnerFirst(
                    f"{field.name} is an owner fact and nobody stated it — "
                    f"{agent.id} asks rather than invents, and an invented "
                    f"answer on a submitted form cannot be taken back")
            if field.required and not (field.value or "").strip():
                raise IncompleteForm(
                    f"{field.name} is required and empty — a half-submitted "
                    f"application cannot be taken back and completed")

    def send(act: outward.Act, *, body: str) -> str:
        precheck(act)
        try:
            entered = driver(url=form.url, fields=form.values(), timeout=timeout)
        except NoTransmitter:
            raise
        except Exception as e:
            raise TransmitFailed(f"the application was not submitted: {e}")
        # what the site actually received, rendered the same way the owner read it
        return "\n".join(f"{name}: {value}" for name, value in entered.items())

    send.precheck = precheck
    return send


def playwright_driver(*, headless: bool = True,
                      available: Optional[Callable[[], bool]] = None
                      ) -> Callable[..., Dict[str, str]]:
    """The real driver. Built, and deliberately never run against a live form.

    It reports what it read back out of each input after typing, so the
    comparison `OWN` makes is against the page's own state rather than against
    our intention.
    """
    def _available() -> bool:
        try:
            import playwright.sync_api          # noqa: F401
            return True
        except Exception:
            return False

    check = available or _available

    def drive(*, url: str, fields: Dict[str, str], timeout: float) -> Dict[str, str]:
        if not check():
            raise NoTransmitter(
                "submitting needs playwright and a browser on this machine: "
                "pip install playwright && playwright install chromium")
        from playwright.sync_api import sync_playwright
        entered: Dict[str, str] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000)
            for name, value in fields.items():
                page.fill(f"[name={name!r}]", value)
            # read back what the page holds, not what we meant to type
            for name in fields:
                entered[name] = page.input_value(f"[name={name!r}]")
            page.click("button[type=submit], input[type=submit]")
            browser.close()
        return entered

    return drive


def dry_run(record: Optional[list] = None) -> Callable[..., str]:
    """Goes through the whole gate and then does not send. What `--dry-run` uses."""
    def send(act: outward.Act, *, body: str) -> str:
        if record is not None:
            record.append({"to": act.destination, "subject": act.subject,
                           "body": body})
        return body
    return send
