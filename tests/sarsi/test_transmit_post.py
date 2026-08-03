"""Publishing — the one act where the approved draft and the published thing
must be shown identical.

`social` has two jobs that must not be confused, and this is the outbound one.
Its rule is sharper than mail's because a platform is an active participant: it
has length limits, it rewrites links, it trims whitespace. Any of those turns
"the owner approved this" into "the owner approved something like this".

So the post transmitter **returns what the platform says it published**, not
what we asked it to publish. If those differ, `OWN`'s approved-bytes check
raises — which is the point. A platform that alters your words should be caught,
not accommodated.

And a post over the limit is **refused, never truncated**: truncating publishes
something nobody approved, and does it in the way most likely to change the
meaning — by removing the end.
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
    vault.put(c, "x.token", "bearer-abc")
    return c


@pytest.fixture
def agent(config):
    return config.agents["social"]


def _act(**kw):
    base = dict(agent_id="social", kind="post", destination="x",
                body="Shipped the export pipeline today. 1,204 rows, verified.")
    base.update(kw)
    return outward.Act(**base)


class FakeHTTP:
    """Stands in for the platform. `echo` is what it claims it published."""

    def __init__(self, *, status=201, echo=None, fails=False):
        self.status, self.fails = status, fails
        self._echo = echo
        self.calls = []

    def __call__(self, *, url, token, payload, timeout):
        if self.fails:
            raise RuntimeError("connection reset")
        self.calls.append({"url": url, "token": token, "payload": payload})
        text = self._echo if self._echo is not None else payload.get("text")
        return self.status, {"text": text, "id": "1234"}


def _post(config, agent, http, platform="x", prompt=None):
    return transmit.post(config, agent, platform=platform, secret="x.token",
                         prompt=prompt or (lambda **kw: "yes"), http=http)


# ── the platform must not alter the words ─────────────────────────────

def test_it_returns_what_the_platform_says_it_published(config, agent):
    http = FakeHTTP()
    act = _act()
    assert _post(config, agent, http)(act, body=act.body) == act.body


def test_a_platform_that_alters_the_text_is_caught_by_the_gate(config, agent):
    """Trimming, re-wrapping, shortening a link — all the same failure."""
    http = FakeHTTP(echo="Shipped the export pipeline today. 1,204 rows, verified")
    with pytest.raises(outward.NotWhatWasApproved):
        outward.request(config, agent, _act(), approve=lambda **kw: "yes",
                        transmit=_post(config, agent, http))


def test_an_altered_post_is_recorded_as_a_mismatch(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    http = FakeHTTP(echo="something else entirely")
    with pytest.raises(outward.NotWhatWasApproved):
        outward.request(config, agent, _act(), approve=lambda **kw: "yes",
                        transmit=_post(config, agent, http))
    assert ledger.count(config, "outward", outcome="mismatch") == 1


def test_the_body_is_sent_exactly_as_written(config, agent):
    http = FakeHTTP()
    act = _act(body="A line.\n\nAnother — with an em dash and https://a.link/x")
    _post(config, agent, http)(act, body=act.body)
    assert http.calls[0]["payload"]["text"] == act.body


# ── limits are refused, never truncated ───────────────────────────────

def test_a_post_over_the_limit_is_refused_not_truncated(config, agent):
    http = FakeHTTP()
    long_body = "x" * 281
    with pytest.raises(transmit.TooLongToPost, match="280"):
        _post(config, agent, http)(_act(body=long_body), body=long_body)
    assert http.calls == []


def test_an_over_limit_post_is_refused_before_the_owner_is_asked(config, agent):
    """Same reasoning as resolving the transmitter before the gate: asking about
    something that cannot be published spends the owner's attention for nothing,
    and the live run did exactly that — it rendered 300 characters and waited."""
    asked = []
    http = FakeHTTP()
    body = "x" * 300
    with pytest.raises(transmit.TooLongToPost):
        outward.request(config, agent, _act(body=body),
                        approve=lambda **kw: asked.append(kw) or "yes",
                        transmit=_post(config, agent, http))
    assert asked == []


def test_an_unsendable_act_is_recorded_as_such(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    body = "x" * 300
    with pytest.raises(transmit.TooLongToPost):
        outward.request(config, agent, _act(body=body),
                        approve=lambda **kw: "yes",
                        transmit=_post(config, agent, FakeHTTP()))
    assert ledger.count(config, "outward", outcome="unsendable") == 1
    assert ledger.count(config, "outward", outcome="sent") == 0


def test_the_refusal_says_how_much_over_it_is(config, agent):
    http = FakeHTTP()
    body = "x" * 300
    with pytest.raises(transmit.TooLongToPost, match="20"):
        _post(config, agent, http)(_act(body=body), body=body)


def test_a_post_at_the_limit_is_sent(config, agent):
    http = FakeHTTP()
    body = "x" * 280
    assert _post(config, agent, http)(_act(body=body), body=body) == body


def test_each_platform_has_its_own_limit(config, agent):
    http = FakeHTTP()
    body = "x" * 500
    # substack has no such limit; the same body goes out
    assert _post(config, agent, http, platform="substack")(
        _act(destination="substack", body=body), body=body) == body


# ── which platforms exist ─────────────────────────────────────────────

def test_an_unknown_platform_is_refused_and_the_known_ones_named(config, agent):
    with pytest.raises(transmit.NoTransmitter, match="mastodon"):
        transmit.post(config, agent, platform="mastodon", secret="x.token",
                      prompt=lambda **kw: "yes", http=FakeHTTP())


def test_the_error_lists_what_it_does_know(config, agent):
    with pytest.raises(transmit.NoTransmitter, match="substack"):
        transmit.post(config, agent, platform="mastodon", secret="x.token",
                      prompt=lambda **kw: "yes", http=FakeHTTP())


# ── credentials and failure ───────────────────────────────────────────

def test_the_token_is_asked_for_at_send_time(config, agent):
    asked = []
    http = FakeHTTP()

    def prompt(**kw):
        asked.append(kw["secret"])
        return "yes"

    act = _act()
    _post(config, agent, http, prompt=prompt)(act, body=act.body)
    assert asked == ["x.token"]
    assert http.calls[0]["token"] == "bearer-abc"


def test_a_denied_token_stops_the_post(config, agent):
    http = FakeHTTP()
    act = _act()
    with pytest.raises(transmit.TransmitFailed, match="x.token"):
        _post(config, agent, http, prompt=lambda **kw: "no")(act, body=act.body)
    assert http.calls == []


def test_a_rejected_post_raises_rather_than_reporting_success(config, agent):
    http = FakeHTTP(status=403)
    act = _act()
    with pytest.raises(transmit.TransmitFailed, match="403"):
        _post(config, agent, http)(act, body=act.body)


def test_a_network_failure_raises(config, agent):
    http = FakeHTTP(fails=True)
    act = _act()
    with pytest.raises(transmit.TransmitFailed, match="connection reset"):
        _post(config, agent, http)(act, body=act.body)


def test_a_platform_that_returns_no_text_is_not_assumed_to_have_published_ours(config, agent):
    """Silence about what was published is not confirmation that it matched."""
    http = FakeHTTP(echo="")
    act = _act()
    with pytest.raises(transmit.TransmitFailed, match="did not confirm"):
        _post(config, agent, http)(act, body=act.body)


# ── through the gate ──────────────────────────────────────────────────

def test_an_approved_post_reaches_the_platform(config, agent):
    http = FakeHTTP()
    out = outward.request(config, agent, _act(), approve=lambda **kw: "yes",
                          transmit=_post(config, agent, http))
    assert out.transmitted is True and len(http.calls) == 1


def test_a_refused_post_never_reaches_the_platform(config, agent):
    http = FakeHTTP()
    outward.request(config, agent, _act(), approve=lambda **kw: "no",
                    transmit=_post(config, agent, http))
    assert http.calls == []


def test_abraham_still_abstains_on_publishing(config):
    """Publishing is a reserved class; abraham holds no standing authority."""
    abraham = config.agents["abraham"]
    http = FakeHTTP()
    out = outward.request(config, abraham,
                          _act(agent_id="abraham", destination="x"),
                          approve=lambda **kw: "yes",
                          transmit=_post(config, abraham, http))
    assert out.abstained is True and http.calls == []
