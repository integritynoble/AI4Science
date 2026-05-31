from __future__ import annotations

from ai4science.harness.events import Message
from ai4science.harness import compaction


def test_no_compact_under_limit():
    hist = [Message(role="user", content="hi"), Message(role="assistant", content="yo")]
    out, did = compaction.maybe_compact(hist, limit_chars=10_000,
                                        summarize=lambda text: "SUMMARY")
    assert did is False and out is hist


def test_compacts_over_limit_preserving_recent():
    hist = [Message(role="user", content="x" * 5000) for _ in range(5)]
    out, did = compaction.maybe_compact(hist, limit_chars=8000, keep_recent=2,
                                        summarize=lambda text: "SUMMARY")
    assert did is True
    assert out[0].role == "system" and "SUMMARY" in out[0].content
    assert out[-2:] == hist[-2:]
    assert len(out) == 3
