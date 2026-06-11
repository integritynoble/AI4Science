"""claude-code mode on the REAL engine (option A) — PWM wrapper units."""
from ai4science.harness import sdk_repl


def test_pwm_for_single_model():
    usage = {"claude-sonnet-4-6": {"input_tokens": 1000, "output_tokens": 1000}}
    pwm, model = sdk_repl._pwm_for(usage, None)
    # ($3 + $15) per M → $0.018 for 1k+1k → /$5 peg = 0.0036 PWM
    assert pwm == 0.0036
    assert model == "claude-sonnet-4-6"


def test_pwm_for_sums_multiple_models():
    usage = {
        "claude-sonnet-4-6": {"input_tokens": 1000, "output_tokens": 0},   # 0.0006
        "claude-fable-5": {"input_tokens": 0, "output_tokens": 1000},      # 0.015
    }
    pwm, _ = sdk_repl._pwm_for(usage, None)
    assert pwm == round(0.0006 + 0.015, 6)


def test_pwm_for_empty_usage_charges_nothing():
    pwm, model = sdk_repl._pwm_for({}, "claude-fable-5")
    assert pwm == 0.0 and model == "claude-fable-5"


def test_sdk_available_requires_cli(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    ok, why = sdk_repl.sdk_available()
    assert ok is False and "claude CLI" in why


def test_sdk_available_true_when_sdk_and_cli_present(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    ok, why = sdk_repl.sdk_available()
    # claude-agent-sdk is installed in this environment
    assert ok is True and why == ""


def test_fmt_tool_shows_args_like_claude_code():
    assert sdk_repl._fmt_tool("Bash", {"command": "ls /home/x"}) == "⏺ Bash(ls /home/x)"
    assert sdk_repl._fmt_tool("Read", {"file_path": "/a/b.md"}) == "⏺ Read(/a/b.md)"
    long = sdk_repl._fmt_tool("Bash", {"command": "x" * 200})
    assert len(long) < 110 and long.endswith("…)")


def test_fmt_tool_todos_checklist():
    out = sdk_repl._fmt_tool("TodoWrite", {"todos": [
        {"content": "write fib.py", "status": "completed"},
        {"content": "run test", "status": "in_progress"}]})
    assert out.startswith("⏺ Todos [1/2]") and "✔ write fib.py" in out and "▸ run test" in out


def test_fmt_result_summarizes():
    import re
    strip = lambda s: re.sub(r"\x1b\[[0-9;]*m", "", s)  # styling (dim/red) is cosmetic
    assert strip(sdk_repl._fmt_result("line1\nline2\nline3", False)) == "  ⎿ line1 (+2 lines)"
    assert strip(sdk_repl._fmt_result("boom", True)) == "  ⎿ ERROR: boom"
    assert sdk_repl._fmt_result("", False) is None


def test_clean_input_strips_terminal_artifacts():
    assert sdk_repl._clean_input("\x1b[O/model\x1b[I") == "/model"
    assert sdk_repl._clean_input("'/model'") == "/model"
    assert sdk_repl._clean_input("\x1b[200~hello\x1b[201~") == "hello"
    assert sdk_repl._clean_input("plain text") == "plain text"
