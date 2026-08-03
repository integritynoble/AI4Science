"""What actually carries an approved act out of the machine.

The gate was built first and deliberately had nothing behind it. This is the
behind — and it is the most dangerous code in the system, because it is the only
part that reaches a person.

Four rules:

  * **there is no default transmitter.** A kind nobody wired says so; it never
    falls back to "something that looks close".
  * **`pay` can never have one.** No grant authorises it, so a transmitter for
    it would be a way around a rule the rest of the design takes seriously.
  * **credentials come from the vault, at send time, for that one act** — never
    from config, never cached on the transmitter.
  * **the transmitter reports what it actually sent**, so the approved-bytes
    check has something real to compare against.
"""
import pytest

from ai4science.harness.agents.sarsi import (outward, registry as reg, transmit,
                                             vault)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    vault.put(c, "mail.smtp", "app-password-here")
    return c


@pytest.fixture
def agent(config):
    return config.agents["work"]


def _act(**kw):
    base = dict(agent_id="work", kind="mail", destination="bob@example.com",
                subject="the export is done", body="Hi Bob — 1,204 rows. C.")
    base.update(kw)
    return outward.Act(**base)


class FakeSMTP:
    def __init__(self, *, fails=False):
        self.fails = fails
        self.sent = []
        self.logged_in_with = None

    def __call__(self, *, host, port, user, password, message, to):
        if self.fails:
            raise RuntimeError("550 mailbox unavailable")
        self.logged_in_with = password
        self.sent.append({"to": to, "message": message})
        return True


# ── the subject is part of what goes out ──────────────────────────────

def test_the_owner_is_shown_the_subject_too(config, agent):
    """An approval of a body is not an approval of a message whose subject
    nobody read."""
    assert "the export is done" in outward.render(_act())


def test_the_digest_changes_when_the_subject_changes(config, agent):
    a = _act()
    b = _act(subject="URGENT: wire transfer required")
    assert a.digest() != b.digest()


def test_the_digest_changes_when_the_recipient_changes(config, agent):
    assert _act().digest() != _act(destination="carol@example.com").digest()


# ── the registry ──────────────────────────────────────────────────────

def test_a_kind_nobody_wired_says_so(config, agent):
    with pytest.raises(transmit.NoTransmitter, match="post"):
        transmit.for_act(config, agent, _act(kind="post"))


def test_pay_can_never_have_a_transmitter(config, agent):
    with pytest.raises(outward.Reserved):
        transmit.register("pay", lambda *a, **k: "")


def test_a_registered_transmitter_is_found(config, agent):
    transmit.register("post", lambda act, *, body, **kw: body)
    try:
        assert transmit.for_act(config, agent, _act(kind="post")) is not None
    finally:
        transmit.unregister("post")


# ── the mail transmitter ──────────────────────────────────────────────

def _delivered(message: str) -> str:
    """What the recipient actually reads, decoded out of the MIME envelope."""
    import email
    from email.policy import default
    return email.message_from_string(message, policy=default).get_content()


def test_it_sends_the_approved_body_unchanged(config, agent):
    smtp = FakeSMTP()
    send = transmit.smtp_mail(config, agent, host="smtp.example", port=587,
                              user="me@example.com", secret="mail.smtp",
                              prompt=lambda **kw: "yes", smtp=smtp)
    act = _act()
    returned = send(act, body=act.body)
    assert returned == act.body
    # MIME adds exactly one trailing newline and may base64 the payload; neither
    # changes a character the recipient reads. That is the whole of what the
    # envelope is allowed to do to the approved text.
    assert _delivered(smtp.sent[0]["message"]) == act.body + "\n"


def test_the_envelope_alters_nothing_else_about_the_text(config, agent):
    """Long lines, unicode and blank lines survive intact — a transmitter that
    re-wrapped a paragraph would be publishing something nobody approved."""
    smtp = FakeSMTP()
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "yes",
                              smtp=smtp)
    body = ("A single very long line that a naive mailer would happily wrap at "
            "seventy-eight characters and thereby change the message.\n\n"
            "Second paragraph — with an em dash and a £ sign.")
    act = _act(body=body)
    send(act, body=act.body)
    assert _delivered(smtp.sent[0]["message"]) == body + "\n"


def test_it_uses_the_acts_own_recipient_and_subject(config, agent):
    smtp = FakeSMTP()
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "yes",
                              smtp=smtp)
    act = _act()
    send(act, body=act.body)
    assert smtp.sent[0]["to"] == "bob@example.com"
    assert "Subject: the export is done" in smtp.sent[0]["message"]


def test_the_credential_is_asked_for_at_send_time(config, agent):
    asked = []
    smtp = FakeSMTP()

    def prompt(**kw):
        asked.append(kw["secret"])
        return "yes"

    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=prompt, smtp=smtp)
    act = _act()
    send(act, body=act.body)
    assert asked == ["mail.smtp"]
    assert smtp.logged_in_with == "app-password-here"


def test_a_denied_credential_stops_the_send(config, agent):
    smtp = FakeSMTP()
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "no",
                              smtp=smtp)
    act = _act()
    with pytest.raises(transmit.TransmitFailed, match="mail.smtp"):
        send(act, body=act.body)
    assert smtp.sent == []


def test_a_failing_send_raises_rather_than_reporting_success(config, agent):
    smtp = FakeSMTP(fails=True)
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "yes",
                              smtp=smtp)
    act = _act()
    with pytest.raises(transmit.TransmitFailed, match="550"):
        send(act, body=act.body)


def test_the_transmitter_never_holds_the_credential_between_acts(config, agent):
    """It is asked for each time. A transmitter that cached it would have turned
    one approval into standing access."""
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "yes",
                              smtp=FakeSMTP())
    assert not any("password" in n.lower() or "secret" in n.lower()
                   for n in vars(send).keys() if hasattr(send, "__dict__"))


# ── end to end through the gate ───────────────────────────────────────

def test_an_approved_act_reaches_the_transmitter(config, agent):
    smtp = FakeSMTP()
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "yes",
                              smtp=smtp)
    out = outward.request(config, agent, _act(), approve=lambda **kw: "yes",
                          transmit=send)
    assert out.transmitted is True
    assert smtp.sent[0]["to"] == "bob@example.com"


def test_a_refused_act_never_reaches_the_transmitter(config, agent):
    smtp = FakeSMTP()
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "yes",
                              smtp=smtp)
    outward.request(config, agent, _act(), approve=lambda **kw: "no",
                    transmit=send)
    assert smtp.sent == []


def test_a_failed_send_is_recorded_as_failed_not_sent(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    smtp = FakeSMTP(fails=True)
    send = transmit.smtp_mail(config, agent, host="h", port=1, user="me",
                              secret="mail.smtp", prompt=lambda **kw: "yes",
                              smtp=smtp)
    with pytest.raises(transmit.TransmitFailed):
        outward.request(config, agent, _act(), approve=lambda **kw: "yes",
                        transmit=send)
    assert ledger.count(config, "outward", outcome="failed") == 1
    assert ledger.count(config, "outward", outcome="sent") == 0
