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
