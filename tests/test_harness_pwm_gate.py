from ai4science.harness import pwm_gate
from ai4science.harness.pwm_gate import PwmGate


def _gate(enabled=True, **kw):
    return PwmGate(token="pwm_k", base="https://x", enabled=enabled, **kw)


def test_disabled_gate_always_allows(monkeypatch):
    g = PwmGate(token=None, base="https://x", enabled=False)
    assert g.check()[0] is True
    assert g.charge(1.0, "0xWALLET", "p", "idem")[0] is True   # no-op


def test_check_allows_with_positive_balance(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_get_balance", lambda: (0.5, ""))
    allowed, reason = g.check()
    assert allowed is True and reason == ""


def test_check_blocks_on_zero_balance(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_get_balance", lambda: (0.0, ""))
    allowed, reason = g.check()
    assert allowed is False and "earn pwm" in reason.lower() and "[pwm]" in reason.lower()


def test_check_blocks_when_balance_unavailable(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_get_balance", lambda: (None, "ssl error"))
    allowed, reason = g.check()
    assert allowed is False and "[pwm]" in reason.lower()


def test_check_reauth_auto_logout_and_short_message(monkeypatch):
    from ai4science import pwm_account
    cleared = []
    monkeypatch.setattr(pwm_account, "clear", lambda: cleared.append(1))
    g = _gate()
    monkeypatch.setattr(g, "_get_balance", lambda: (None, "reauth"))
    allowed, reason = g.check()
    assert allowed is False
    assert "login" in reason and "logged out" in reason
    assert cleared, "clear() should have been called"
    # Must NOT contain the long _EARN paragraph
    assert "mine on" not in reason.lower()


def test_charge_posts_spend(monkeypatch):
    g = _gate()
    seen = {}
    def fake_post(path, body):
        seen["path"] = path; seen["body"] = body
        return 200, {"success": True, "balance_after": 0.4}
    monkeypatch.setattr(g, "_post", fake_post)
    ok, reason = g.charge(0.1, "0xWALLET", "ai4science:common:gpt", "sid:1")
    assert ok is True
    assert seen["path"] == "/api/v1/pwm-token/spend"
    assert seen["body"]["amount"] == 0.1 and seen["body"]["provider_wallet"] == "0xWALLET"
    assert seen["body"]["idempotency_key"] == "sid:1"


def test_charge_402_reports_exhausted(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_post", lambda path, body: (402, {"detail": "insufficient"}))
    ok, reason = g.charge(0.1, "0xW", "p", "idem")
    assert ok is False and "[pwm]" in reason.lower()


def test_charge_zero_amount_is_noop(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_post", lambda p, b: (_ for _ in ()).throw(AssertionError("no post")))
    assert g.charge(0.0, "0xW", "p", "idem")[0] is True


def test_from_env_auto_enabled_when_logged_in(monkeypatch):
    # Logged in (token present) → gate ON automatically, no flag needed.
    monkeypatch.delenv("AI4SCIENCE_PWM_GATE", raising=False)
    monkeypatch.setenv("PWM_TOKEN", "pwm_k")
    assert PwmGate.from_env().enabled is True
    # Explicit flag still works and still needs a token.
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "1")
    assert PwmGate.from_env().enabled is True
    # AI4SCIENCE_PWM_GATE=0 is the explicit opt-out, even with a token.
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "0")
    assert PwmGate.from_env().enabled is False
    # No token → always off (dev/CI run free), regardless of the flag.
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "1")
    monkeypatch.delenv("PWM_TOKEN", raising=False)
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    from ai4science import pwm_account
    monkeypatch.setattr(pwm_account, "load", lambda: None)
    assert PwmGate.from_env().enabled is False
