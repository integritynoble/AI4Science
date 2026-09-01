"""The gateway half of the ACP stall: a key that named the wrong agent.

`openclaw acp` is a bridge backed by the Gateway, and its `--session` takes a
key in the grammar `agent:<agent>:<session>` — the format of every key in the
live store and every example in openclaw's own dist:

    agent:main:main          agent:ops:work          agent:my-agent:my-session

`openclaw_acp_runtime` emitted `f"{agent_id}:main:main"` — no `agent:` prefix.

What that did is worth stating exactly, because the first version of this file
guessed and guessed wrong. It did **not** "resolve to nothing". openclaw read
the unprefixed string as a SESSION NAME under the DEFAULT agent and created it.
The live store still holds the evidence:

    agent:main:sarsi-claude:main:main
        origin.label      "ACP"
        totalTokens       0
        lastInteractionAt == sessionStartedAt

So the bridge came up attached to agent `main` — a different model entirely —
under a junk session name, and no prompt ever reached an engine. That is the
measured stall: a genuinely-ours openclaw process alive 85 minutes, the task
still `planning`, the reports ledger empty.

Underneath the key was a plainer fact: **no `sarsi-claude` agent existed.**
`openclaw agents list` held `main` and `ops`. The prefix bug is what stopped
that from being visible, so the fix is both — emit a well-formed key, and
refuse to spawn for an agent the gateway does not have.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import acp


@pytest.fixture(autouse=True)
def fresh_runtime_cache():
    """`_get_runtime` caches by command tuple; a test that changes the command
    must not read another test's cached runtime."""
    before = dict(acp._runtimes)
    acp._runtimes.clear()
    yield
    acp._runtimes.clear()
    acp._runtimes.update(before)


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    """A config of our own.

    The agent check reads `~/.openclaw/openclaw.json`, and a test that read the
    REAL one would pass or fail on whether this machine happens to have
    `sarsi-claude` registered — machine state walking into an assertion.
    """
    d = tmp_path / ".openclaw"
    d.mkdir()
    (d / "openclaw.json").write_text(json.dumps(
        {"agents": {"list": [{"id": "ops"}, {"id": "sarsi-claude"},
                             {"id": "sarsi-ai4sci"}]}}))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _argv(agent_id="sarsi-claude"):
    """The argv the runtime was built with, read off the cache key."""
    acp.openclaw_acp_runtime(agent_id)
    return list(next(k for k in acp._runtimes if agent_id in " ".join(k)))


# ── the key ────────────────────────────────────────────────────────────────

def test_the_session_key_carries_the_agent_prefix():
    """Without the prefix openclaw files the session under the DEFAULT agent
    and runs the task on whatever model that agent uses."""
    argv = _argv("sarsi-claude")

    assert "--session" in argv
    key = argv[argv.index("--session") + 1]
    assert key.startswith("agent:"), key
    assert key.split(":")[1] == "sarsi-claude", key


def test_the_session_component_is_stable_across_calls():
    """The bridge resolves a key to a stored conversation. A key that changed
    per call would start a new session every time and lose the history the
    gateway exists to keep."""
    assert _argv("sarsi-claude") == _argv("sarsi-claude")


def test_two_agents_do_not_share_a_session():
    a = _argv("sarsi-claude")
    b = _argv("sarsi-ai4sci")

    assert a[a.index("--session") + 1] != b[b.index("--session") + 1]


# ── the flag that was the wrong answer ─────────────────────────────────────

def test_require_existing_is_not_passed():
    """This asserts the ABSENCE of a flag, so it needs its reason on the
    record.

    `--require-existing` was the first fix here, on the reasoning that a key
    resolving to nothing should fail rather than idle. Probed against the live
    bridge with a never-used key, it makes `session/new` return:

        No session found: agent:sarsi-claude:brand-new-never-used

    The flag is about the SESSION, and a freshly registered agent has none — so
    passing it turns every FIRST run on a new machine into a hard failure. It
    checks the wrong noun: what has to already exist is the AGENT.
    """
    assert "--require-existing" not in _argv("sarsi-claude")


# ── the noun that does have to exist ───────────────────────────────────────

def test_an_agent_the_gateway_does_not_have_fails_before_it_spawns():
    """The root cause, caught directly: nothing named `sarsi-claude` was ever
    registered, and the malformed key hid it for 85 minutes."""
    with pytest.raises(acp.AcpError) as e:
        acp.openclaw_acp_runtime("sarsi-nobody")

    msg = str(e.value)
    assert "sarsi-nobody" in msg
    assert "openclaw agents add" in msg, "must name the fix, not just the fault"


def test_a_configured_agent_spawns_without_complaint():
    """The check must not become a second way for the path to stall."""
    assert _argv("sarsi-claude")


def test_the_default_agent_counts_as_configured(fake_home):
    """`main` is served whether or not the list names it — and this config's
    list does not. Treating it as missing would break the fallback agent."""
    acp.openclaw_acp_runtime("main")


def test_an_unreadable_config_is_not_evidence_of_a_missing_agent(monkeypatch,
                                                                 tmp_path):
    """Absence of evidence is not evidence of absence — the same rule the
    session-store lookup follows. A machine with no openclaw config must not
    have its spawn refused on the strength of a file that isn't there."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))

    assert acp.openclaw_agent_ids() is None
    acp.openclaw_acp_runtime("anything-at-all")


# ── the handshake has to outlast a cold start ──────────────────────────────

def test_the_connect_timeout_survives_a_cold_handshake():
    """The nightly gate failed attempt 1 on EVERY scheduled run, always with
    `no response to initialize`, always passing on the retry.

    That is not a flake, it is the cost of first contact. Measured on the box,
    two connections back to back: cold `initialize` 39.81s, warm 7.09s, with
    `session/new` fast either way — so the wait is the agent runtime waking,
    not the protocol.

    The old 30s could not pass a cold handshake. This asserts the ceiling stays
    clear of the measurement rather than asserting an exact number, because the
    point is the margin: a value that merely squeaks past 40s would put the
    nightly gate back on a knife edge.
    """
    assert acp.CONNECT_TIMEOUT >= 120, (
        f"CONNECT_TIMEOUT={acp.CONNECT_TIMEOUT}s leaves no room over a cold "
        f"handshake measured at ~40s")

    # Read the SOURCE, not the live attribute.
    #
    # `conftest._no_real_acp_spawn` replaces `AcpClient.connect` with a refusal
    # stub for every test, and that stub carries its own `timeout: float = 30.0`.
    # Introspecting the bound method here therefore reports the guard's default
    # and never the code's — the first version of this test failed against
    # `30.0 == 180` while the module was already correct.
    import inspect
    src = inspect.getsource(acp)
    assert "def connect(self, timeout: float = CONNECT_TIMEOUT)" in src, \
        "connect() must take its default from the documented constant, so the "\
        "measurement and the value cannot drift apart"
