"""codex mode on the REAL engine — PWM wrapper units."""
import json

from ai4science.harness import codex_repl


def test_handle_event_thread_and_usage():
    st = {}
    codex_repl.handle_event(json.dumps(
        {"type": "thread.started", "thread_id": "t-123"}), st)
    codex_repl.handle_event(json.dumps(
        {"type": "turn.completed",
         "usage": {"input_tokens": 1000, "output_tokens": 100}}), st)
    assert st["thread_id"] == "t-123"
    assert st["usage"]["output_tokens"] == 100


def test_handle_event_messages_and_tools():
    st = {}
    out = codex_repl.handle_event(json.dumps(
        {"type": "item.completed",
         "item": {"type": "agent_message", "text": "hi"}}), st)
    assert out == "hi"
    out = codex_repl.handle_event(json.dumps(
        {"type": "item.completed",
         "item": {"type": "mcp_tool_call", "tool": "compute_providers"}}), st)
    assert "[tool] compute_providers" in out
    assert st["tools"] == ["compute_providers"]
    assert codex_repl.handle_event("not json", st) is None


def test_pwm_for_uses_gpt55_pricing():
    # gpt-5.5: $1.25/$10 per M → 1k in + 1k out = $0.01125 → /$5 = 0.00225 PWM
    assert codex_repl._pwm_for(
        {"input_tokens": 1000, "output_tokens": 1000}) == 0.00225


def test_turn_cmd_modes():
    base = codex_repl._turn_cmd("hi", thread_id=None, read_only=False,
                                model=None, gpu_optin=False)
    assert "--full-auto" in base and base[-1] == "hi"
    ro = codex_repl._turn_cmd("hi", thread_id=None, read_only=True,
                              model=None, gpu_optin=False)
    assert "read-only" in ro
    trust = codex_repl._turn_cmd("hi", thread_id=None, read_only=False,
                                 model=None, gpu_optin=False, auto_yes=True)
    assert "--dangerously-bypass-approvals-and-sandbox" in trust
    res = codex_repl._turn_cmd("hi", thread_id="t-1", read_only=False,
                               model="gpt-5.5", gpu_optin=True)
    assert res[1:4] == ["exec", "resume", "t-1"] or res[2:4] == ["resume", "t-1"]
    assert "-m" in res and "gpt-5.5" in res


def test_engine_available_requires_cli(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    ok, why = codex_repl.codex_engine_available()
    assert ok is False and "codex CLI" in why
