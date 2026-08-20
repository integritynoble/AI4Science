"""A spawn must report the TRUTH, from the return value alone.

THE DEFECT THIS IS WRITTEN FOR.

An ACP spawn that does not cleanly acknowledge collapses three different
realities into one uninformative string ("The operation timed out"):

    (a) the session STARTED and is RUNNING     -- the ack was just slow
    (b) the session STARTED and has FINISHED   -- it even completed
    (c) the session NEVER STARTED              -- nothing exists

A caller handed that one string cannot retry safely, cannot attach, and cannot
tell a lost handle from a dead spawn. The remedy is a spawn wrapper that, when
the spawn call raises or times out, does NOT propagate the bare timeout. It
LOOKS THE SESSION UP by the key it was given and returns a structured result
carrying both a handle and a lifecycle status.

THE INVARIANT THAT MUST NOT BE BROKEN.

`never_started` is a POSITIVE claim -- "I looked and there is no session". It may
only be returned on a genuine NEGATIVE lookup. If the lookup itself cannot be
done (no lookup configured, or the lookup raises), we do NOT get to say
never_started: absence of evidence is not evidence of absence. That case reports
`unknown`, honestly, rather than the convenient lie.

Runs on stdlib unittest against an injected spawn and an injected lookup. No
subprocess, no gateway, no network -- a test that needs a live gateway is a test
that dies with the gateway.
"""
import unittest

from ai4science.harness.agents.sarsi import acp_backend as acp


class FakeConnection:
    """A spawn that succeeds and hands back a session id. Written in the test,
    not borrowed from the code under test."""

    def __init__(self, *, session_id="sid-run-1"):
        self.session_id = session_id
        self.closed = False

    def initialize(self):
        return {"protocolVersion": 1}

    def new_session(self, cwd, env=None):
        self.cwd = cwd
        return self.session_id

    def close(self):
        self.closed = True


class FailingConnection(FakeConnection):
    """A spawn whose session/new never acknowledges -- the timeout shape. The
    session may nonetheless be alive on the gateway; only a lookup can tell."""

    def new_session(self, cwd, env=None):
        raise TimeoutError("The operation timed out")


def _quiet_wire(*_a, **_k):
    """Governance is a separate concern; keep it out of these tests so the
    subject is purely the three-way truth."""
    return None


def _runtime(*, conn, lookup=None):
    return acp.AcpRuntime(connect=lambda **_: conn, agent_id="sarsi-ai4sci",
                          lookup=lookup, wire=_quiet_wire)


class _Cleared(unittest.TestCase):
    def setUp(self):
        acp._LIVE.clear()

    def tearDown(self):
        acp._LIVE.clear()


class TheThreeStatusesAreDistinct(_Cleared):
    def test_running_finished_never_started_are_three_different_strings(self):
        names = [acp.RUNNING, acp.FINISHED, acp.NEVER_STARTED]
        self.assertEqual(len(set(names)), 3, names)


class ACleanSpawnReportsRunning(_Cleared):
    def test_a_spawn_that_acknowledges_is_running_and_carries_its_handle(self):
        rt = _runtime(conn=FakeConnection(session_id="sid-live"))
        out = rt.spawn("task-A", "/tmp", govern=False, ceiling="A0")
        self.assertEqual(out["status"], acp.RUNNING, out)
        self.assertEqual(out["session_key"], "task-A", out)
        self.assertEqual(out.get("acp_session_id"), "sid-live", out)


class ATimeoutWhereTheSessionIsLiveReportsRunning(_Cleared):
    def test_a_lost_ack_over_a_live_session_is_running_not_a_bare_timeout(self):
        seen = {}

        def lookup(key):
            seen["key"] = key
            return {"state": "running", "acp_session_id": "sid-found"}

        rt = _runtime(conn=FailingConnection(), lookup=lookup)
        out = rt.spawn("task-B", "/tmp", govern=False, ceiling="A0")

        self.assertEqual(out["status"], acp.RUNNING, out)
        self.assertEqual(out["session_key"], "task-B", out)
        self.assertEqual(out.get("acp_session_id"), "sid-found", out)
        self.assertEqual(seen.get("key"), "task-B", "the lookup used the key")
        # The truth is carried by the STATUS, not a bare string. The detail may
        # still quote the underlying cause for diagnostics -- what matters is
        # that the reply also evidences the live session, so the caller is not
        # handed the timeout string ALONE.
        self.assertIn("live", (out.get("detail") or "").lower())


class ATimeoutWhereTheSessionFinishedReportsFinished(_Cleared):
    def test_a_lost_ack_over_a_finished_session_is_finished(self):
        rt = _runtime(conn=FailingConnection(),
                      lookup=lambda key: {"state": "finished",
                                          "acp_session_id": "sid-done"})
        out = rt.spawn("task-C", "/tmp", govern=False, ceiling="A0")
        self.assertEqual(out["status"], acp.FINISHED, out)
        self.assertEqual(out["session_key"], "task-C", out)


class NeverStartedIsOnlyClaimedOnANegativeLookup(_Cleared):
    def test_a_genuine_negative_lookup_reports_never_started(self):
        rt = _runtime(conn=FailingConnection(), lookup=lambda key: None)
        out = rt.spawn("task-D", "/tmp", govern=False, ceiling="A0")
        self.assertEqual(out["status"], acp.NEVER_STARTED, out)
        self.assertEqual(out["session_key"], "task-D", out)
        self.assertIn("task-D", out.get("detail") or "")


class NeverStartedIsNeverGuessedWithoutEvidence(_Cleared):
    """The core invariant: absence of evidence is not a negative lookup."""

    def test_a_lookup_that_raises_does_not_become_never_started(self):
        def lookup(key):
            raise RuntimeError("gateway unreachable")

        rt = _runtime(conn=FailingConnection(), lookup=lookup)
        out = rt.spawn("task-E", "/tmp", govern=False, ceiling="A0")
        self.assertNotEqual(out["status"], acp.NEVER_STARTED,
                            "a failed lookup must never be read as 'no session'")
        self.assertEqual(out["status"], acp.UNKNOWN, out)
        self.assertEqual(out["session_key"], "task-E", out)

    def test_no_lookup_configured_does_not_become_never_started(self):
        rt = _runtime(conn=FailingConnection(), lookup=None)
        out = rt.spawn("task-F", "/tmp", govern=False, ceiling="A0")
        self.assertNotEqual(out["status"], acp.NEVER_STARTED,
                            "with no way to look, never_started is a guess")
        self.assertEqual(out["status"], acp.UNKNOWN, out)


class SpawnNeverPropagatesABareTimeout(_Cleared):
    """Whatever happens, the caller gets a status dict -- never an exception
    escaping with the uninformative platform string."""

    def test_a_spawn_timeout_returns_a_status_rather_than_raising(self):
        rt = _runtime(conn=FailingConnection(), lookup=lambda key: None)
        try:
            out = rt.spawn("task-G", "/tmp", govern=False, ceiling="A0")
        except Exception as e:  # noqa: BLE001 -- the whole point is it must not
            self.fail(f"spawn propagated a bare exception: {type(e).__name__}: {e}")
        self.assertIn("status", out)


if __name__ == "__main__":
    unittest.main()
