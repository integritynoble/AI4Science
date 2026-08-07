"""A tripwire halts a WORKER session. It must not halt the owner's own.

The catastrophe backstop persists a per-session flag, and every later tool call
in that session is denied with "session halted by an earlier tripwire". For a
governed worker session that is right: an unattended agent that reached for a
forbidden command should stop until the owner looks.

For the owner's OWN session it is wrong, and the difference is not theoretical.
`ensure_governance_hook` installs the hook into a project directory. Anyone who
later runs a coding agent in that directory — the owner, at a terminal, working
by hand — inherits it. On 2026-08-07 that happened: a `-halt-on-error` FLAG
matched the pattern for the `halt` COMMAND, and the owner's session was killed
for the rest of its life. Every subsequent tool call, including reading a file,
returned the halt.

The pattern was fixed. The blast radius was not, and the blast radius is the
real defect: a false positive in a regex should cost one denied command, not an
entire working session.

**What does not change.** The deny still stands. A forbidden command is refused
in every session, worker or owner. What is scoped is only the PERSISTENT HALT —
the part that punishes every later, unrelated call.

The discriminator is the one the hook already computes: a governed worker
session has a supervisor record; a session someone started by hand does not.
"""
import pytest

from ai4science.harness.agents.machine import hook


def _forbidden():
    return {"decision": "deny", "reason": "forbidden command", "tripwire": True}


# ── the deny is never traded away ─────────────────────────────────────

def test_a_forbidden_command_is_denied_in_every_session():
    """Scoping the halt must not weaken the refusal. This is the invariant the
    change is allowed to keep and nothing else."""
    assert hook.should_deny(_forbidden()) is True


# ── but the persistent halt is scoped ─────────────────────────────────

def test_a_worker_session_is_halted():
    """It has a supervisor record: something started it on the owner's behalf
    and nobody is watching it."""
    rec = {"name": "sarsi-worker-abcd", "ceiling": "A1"}
    assert hook.should_halt_session(_forbidden(), rec) is True


def test_the_owners_own_session_is_not():
    """No supervisor record — a human started this and is sitting at it. Deny
    the command; do not end the session."""
    assert hook.should_halt_session(_forbidden(), None) is False


def test_a_non_tripwire_deny_halts_nothing():
    ordinary = {"decision": "deny", "reason": "beyond the ceiling",
                "tripwire": False}
    assert hook.should_halt_session(ordinary, {"name": "sarsi-worker-abcd"}) is False
    assert hook.should_halt_session(ordinary, None) is False


def test_an_allow_halts_nothing():
    ok = {"decision": "allow", "reason": "in-project write", "tripwire": False}
    assert hook.should_halt_session(ok, {"name": "sarsi-worker-abcd"}) is False


# ── the record of the attempt survives either way ─────────────────────

def test_the_attempt_is_still_recorded_for_an_owner_session():
    """Scoping the halt must not scope the EVIDENCE. A forbidden command was
    tried; that it was tried is exactly what an owner would never think to
    check for, and exactly what must not go missing."""
    assert hook.should_record_attempt(_forbidden()) is True


def test_and_for_a_worker_session():
    assert hook.should_record_attempt(_forbidden()) is True
