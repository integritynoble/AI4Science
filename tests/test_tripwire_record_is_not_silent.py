"""A tripwire that could not be recorded says so in the verdict.

The catastrophe backstop fires, and then:

    if verdict.get("tripwire"):
        _set_tripped(session_id, ...)
        try: _trust.record("forbidden")   # voids A3 eligibility
        except Exception: pass
        try: _sup.update(rec["name"], tripwire=True, ...)   # `session ls` shows TRIPPED
        except Exception: pass

The **deny still happens** — the verdict is printed either way, so the command
is blocked. What can vanish is the *record of the attempt*: the trust ledger
entry that voids A3 eligibility, and the supervisor flag that makes a tripped
session visible in `session ls`. Both silently.

That is the worst kind of silence in this file. A forbidden command was tried;
the owner's evidence that it was tried is exactly what an attacker would want
missing, and exactly what a distracted owner would never think to check for.

**Refusing is not available here.** The hook is a subprocess Claude Code
depends on: raising would leave it with no verdict at all, which is a worse
failure than an unrecorded one. So the failure is not swallowed and not
escalated — it is put in the **reason**, which is the one channel that always
reaches the surface.
"""
import json

import pytest

from ai4science.harness.agents.machine import hook


class Boom:
    def record(self, *a, **kw):
        raise OSError("read-only ledger")

    def update(self, *a, **kw):
        raise OSError("supervisor store is gone")

    def effective_ceiling(self, c):
        return c


def _tripwire_verdict():
    return {"decision": "deny", "reason": "forbidden command",
            "tripwire": True}


# ── the block is never traded away ────────────────────────────────────

def test_the_deny_still_stands_when_nothing_can_be_recorded():
    got = hook._note_record_failures(_tripwire_verdict(),
                                     ["the trust ledger", "the session record"])
    assert got["decision"] == "deny"
    assert got["tripwire"] is True


# ── but the gap is stated ─────────────────────────────────────────────

def test_a_failed_trust_entry_reaches_the_reason():
    got = hook._note_record_failures(_tripwire_verdict(), ["the trust ledger"])
    assert "trust ledger" in got["reason"]
    assert "could not be recorded" in got["reason"].lower()


def test_and_a_failed_session_flag_too():
    got = hook._note_record_failures(_tripwire_verdict(),
                                     ["the session record"])
    assert "session record" in got["reason"]


def test_both_are_named_when_both_fail():
    got = hook._note_record_failures(_tripwire_verdict(),
                                     ["the trust ledger", "the session record"])
    assert "trust ledger" in got["reason"]
    assert "session record" in got["reason"]


def test_the_original_reason_survives():
    """What was forbidden matters as much as the fact the note failed."""
    got = hook._note_record_failures(_tripwire_verdict(), ["the trust ledger"])
    assert "forbidden command" in got["reason"]


def test_nothing_is_added_when_everything_recorded():
    got = hook._note_record_failures(_tripwire_verdict(), [])
    assert got["reason"] == "forbidden command"


# ── through the tripwire path ─────────────────────────────────────────

def test_a_tripwire_whose_record_fails_is_not_silent(monkeypatch, capsys,
                                                     tmp_path):
    """End to end: a forbidden command, with both record stores broken."""
    monkeypatch.setattr(hook, "_set_tripped", lambda *a, **kw: None)
    monkeypatch.setattr(hook, "_session_ceiling",
                        lambda *a, **kw: ("A1", {"name": "s"}))
    monkeypatch.setattr(hook, "decide_tool_call",
                        lambda *a, **kw: _tripwire_verdict())
    import ai4science.harness.agents.machine.trust as trust
    import ai4science.harness.agents.machine.supervisor as sup
    monkeypatch.setattr(trust, "record", Boom().record)
    monkeypatch.setattr(trust, "effective_ceiling", lambda c: c)
    monkeypatch.setattr(sup, "update", Boom().update)

    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps({
        "tool_name": "Bash", "tool_input": {"command": "rm -rf /"},
        "cwd": str(tmp_path), "session_id": "s1"})))
    hook.main()
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    text = json.dumps(out)
    assert "could not be recorded" in text.lower(), out
