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


# ── compaction never breaks a tool exchange or drops the system prompt ────

from ai4science.harness.events import ToolCall


def _exchange(i, size=3000):
    return [Message(role="user", content=f"u{i} " + "x" * size),
            Message(role="assistant", content="", tool_calls=[ToolCall(f"c{i}", "read", {"path": "a"})]),
            Message(role="tool", content="r" * size, tool_call_id=f"c{i}"),
            Message(role="assistant", content=f"a{i}")]


def _valid(history):
    answered = {m.tool_call_id for m in history if m.role == "tool"}
    for m in history:
        if m.role == "assistant":
            assert all(tc.id in answered for tc in m.tool_calls)
    seen_assistant = set()
    for m in history:
        if m.role == "assistant":
            seen_assistant |= {tc.id for tc in m.tool_calls}
        elif m.role == "tool":
            assert m.tool_call_id in seen_assistant, "tool result before its call"


def test_cut_aligns_to_a_user_turn_so_no_tool_exchange_is_split():
    hist = [Message(role="system", content="MODE PROMPT")]
    for i in range(5):
        hist += _exchange(i)
    out, did = compaction.maybe_compact(hist, limit_chars=10_000, keep_recent=6,
                                        summarize=lambda t: "SUMMARY")
    assert did
    _valid(out)
    assert out[0].content == "MODE PROMPT"                   # kept verbatim, first
    assert out[1].role == "system" and "SUMMARY" in out[1].content
    assert out[2].role == "user"                             # the tail starts a turn
    assert out[2].content.startswith("u3") and out[-1].content == "a4"   # 6 back → aligned to u3


def test_summarizer_failure_or_empty_summary_leaves_history_alone():
    hist = [Message(role="user", content="x" * 5000) for _ in range(5)]
    out, did = compaction.maybe_compact(hist, limit_chars=8000, keep_recent=2,
                                        summarize=lambda t: (_ for _ in ()).throw(RuntimeError("529")))
    assert did is False and out is hist
    out, did = compaction.maybe_compact(hist, limit_chars=8000, keep_recent=2,
                                        summarize=lambda t: "   ")
    assert did is False and out is hist


def test_zero_limit_disables():
    hist = [Message(role="user", content="x" * 5000) for _ in range(5)]
    assert compaction.maybe_compact(hist, limit_chars=0, summarize=lambda t: "S")[1] is False


def test_repeated_compaction_keeps_one_leading_prompt_and_stays_valid():
    hist = [Message(role="system", content="MODE PROMPT")]
    for i in range(12):
        hist += _exchange(i)
        hist, _ = compaction.maybe_compact(hist, limit_chars=20_000, keep_recent=4,
                                           summarize=lambda t: "S" * 100)
        _valid(hist)
    assert hist[0].content == "MODE PROMPT"
    assert sum(1 for m in hist if m.role == "system") == 2
    assert sum(len(m.content) for m in hist) < 40_000
