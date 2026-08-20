"""Port B->A: the persistent transport (`acp`) must also speak the FOUR
outcomes, not a bare ok/stopReason pair.

Side A returned `{"ok": True, "stopReason": ...}` and left the caller to guess
whether a `refusal` was a success or a failure — the exact ambiguity the
screen-scorer got wrong and `acp_backend.classify` was written to remove. The
verdict logic lives in `acp_backend`; `acp` must reuse it (shared, not
re-implemented) so a REFUSED reads ok=True on BOTH transports.
"""
from ai4science.harness.agents.sarsi import acp
from ai4science.harness.agents.sarsi import acp_backend


def test_acp_reexports_the_shared_verdict_functions():
    # Shared, not re-implemented: same function object on both modules.
    assert acp.classify is acp_backend.classify
    assert acp.verdict_of is acp_backend.verdict_of


class _FakeClient:
    """A live client whose one prompt returns a fixed A-shaped reply."""
    alive = True

    def __init__(self, reply):
        self._reply = reply

    def prompt(self, text, timeout=None):
        return dict(self._reply)


def _runtime_with(reply):
    rt = acp.AcpRuntime()
    rt._clients["t"] = _FakeClient(reply)
    return rt


def test_send_marks_a_refusal_as_a_correct_outcome():
    """A `refusal` stop reason is REFUSED with ok=True — not a failure."""
    out = _runtime_with({"ok": True, "stopReason": "refusal",
                         "text": "I will not do that"}).send("t", "hi")
    assert out["outcome"] == acp_backend.REFUSED
    assert out["ok"] is True
    assert out["refused"] is True


def test_send_marks_end_turn_as_answered():
    out = _runtime_with({"ok": True, "stopReason": "end_turn",
                         "text": "done"}).send("t", "hi")
    assert out["outcome"] == acp_backend.ANSWERED
    assert out["ok"] is True


def test_send_marks_a_transport_failure_as_errored():
    out = _runtime_with({"ok": False,
                         "reason": "prompt timed out after 600s"}).send("t", "hi")
    assert out["outcome"] == acp_backend.ERRORED
    assert out["ok"] is False


def test_send_marks_no_turn_as_silent():
    out = _runtime_with({"ok": True, "stopReason": None,
                         "text": ""}).send("t", "hi")
    assert out["outcome"] == acp_backend.SILENT
