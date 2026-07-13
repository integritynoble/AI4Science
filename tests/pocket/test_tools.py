from ai4science.harness.agents.pocket.tools import (
    default_registry,
    consequential_kind,
    CONSEQUENTIAL_KINDS,
)


def _tool(name):
    return next(t for t in default_registry() if t.name == name)


def test_registry_is_closed_and_low_risk():
    reg = default_registry()
    # every tool is one of the four low-risk side-effect classes — no code exec.
    assert all(t.side_effect in {"read", "reversible_write", "notification", "none"} for t in reg)
    # advise carries no permission and is the fallback (no keywords).
    advise = _tool("advise")
    assert advise.permission == "" and advise.match == ()


def test_note_write_then_read_round_trip():
    ctx = {}
    w = _tool("note_write").fn("buy milk", ctx)
    assert w == {"written": "buy milk", "count": 1}
    r = _tool("note_read").fn("my notes", ctx)
    assert r == {"notes": ["buy milk"]}


def test_reminder_create_appends():
    ctx = {}
    out = _tool("reminder_create").fn("call mom", ctx)
    assert out == {"created": "call mom", "count": 1}
    assert ctx["reminders"] == ["call mom"]


def test_calendar_read_is_read_only():
    ctx = {"calendar": [{"t": "10:00", "title": "standup"}]}
    out = _tool("calendar_read").fn("what's on today", ctx)
    assert out == {"events": [{"t": "10:00", "title": "standup"}]}
    # unchanged
    assert ctx["calendar"] == [{"t": "10:00", "title": "standup"}]


def test_capability_status_reads_graph():
    ctx = {"capabilities": {"algebra": 0.8}}
    assert _tool("capability_status").fn("my progress", ctx) == {"capabilities": {"algebra": 0.8}}


def test_advise_returns_text():
    assert _tool("advise").fn("  what's the weather  ", {}) == "advisory: what's the weather"


def test_consequential_kind_detects_and_defaults_none():
    assert consequential_kind("pay $20 to Bob") == "spend"
    assert consequential_kind("publish this to my blog") == "publish"
    assert consequential_kind("deploy to production") == "deploy"
    assert consequential_kind("jot down a grocery note") is None
    assert consequential_kind("") is None
    # every detected kind is in the declared set
    for intent in ("buy it", "post it", "wipe the remote", "release now", "log in to gmail"):
        k = consequential_kind(intent)
        assert k is None or k in CONSEQUENTIAL_KINDS
