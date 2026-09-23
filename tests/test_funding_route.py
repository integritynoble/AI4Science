"""Free BYOK is a route, not a discount (ticket F01 of the September 21 plan).

The user's own LLM costs 0 PWM, needs no PWM login, reads no balance, and is
never switched to the paid route — not because a backend has no key here, not
after a failure, and not because a PWM token happens to be remembered. The
paid route is selected, by the user, or by a PWM login being the only
credential there is.
"""
import pytest

from ai4science import funding


@pytest.fixture
def clean(tmp_path, monkeypatch):
    """No credential of any kind, no selection, no env switch."""
    monkeypatch.setenv("AI4SCIENCE_USER_CONFIG", str(tmp_path / "user.json"))
    monkeypatch.setenv("AI4SCIENCE_KEYS", str(tmp_path / "keys.json"))
    monkeypatch.setenv("AI4SCIENCE_PWM_ACCOUNT", str(tmp_path / "pwm_account.json"))
    for var in ("AI4SCIENCE_FUNDING", "AI4SCIENCE_PWM_GATE", "PWM_TOKEN",
                "PWM_ONBOARD_TOKEN", "PWM_BASE", "PWM_ONBOARD_BASE", "PWM_NO_PROXY"):
        monkeypatch.delenv(var, raising=False)
    from ai4science.harness.adapters import creds
    monkeypatch.setattr(creds, "available", lambda b: False)
    from ai4science.harness.adapters import factory
    monkeypatch.setattr(factory, "_NOTICED_OWN_KEY", set())
    return tmp_path


def _own_login():
    from ai4science import user as user_cfg
    user_cfg.login_own("anthropic", "subscription")


def _pwm_login():
    from ai4science import pwm_account
    pwm_account.save(base="https://x.example", token="pwm_t")


# ── resolution ───────────────────────────────────────────────────────

def test_nothing_configured_is_the_free_route(clean):
    r = funding.resolve()
    assert r.route == funding.OWN and not r.pays_pwm and not r.explicit


def test_own_login_is_the_free_route_even_with_a_pwm_login(clean):
    _own_login()
    _pwm_login()
    r = funding.resolve()
    assert r.route == funding.OWN and not r.explicit


def test_a_stored_key_counts_as_an_own_credential(clean):
    from ai4science import user as user_cfg
    user_cfg.set_api_key("gemini", "k")
    _pwm_login()
    assert funding.resolve().route == funding.OWN


def test_an_env_key_counts_as_an_own_credential(clean, monkeypatch):
    from ai4science.harness.adapters import creds
    monkeypatch.setattr(creds, "available", lambda b: b == "deepseek")
    _pwm_login()
    assert funding.resolve().route == funding.OWN


def test_pwm_login_alone_selects_pwm(clean):
    _pwm_login()
    r = funding.resolve()
    assert r.route == funding.PWM and not r.explicit


def test_env_token_alone_selects_pwm(clean, monkeypatch):
    monkeypatch.setenv("PWM_TOKEN", "pwm_env")
    assert funding.resolve().route == funding.PWM


def test_gate_off_keeps_a_token_only_machine_free(clean, monkeypatch):
    monkeypatch.setenv("PWM_TOKEN", "pwm_env")
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "0")
    assert funding.resolve().route == funding.OWN


def test_explicit_selection_beats_credentials(clean):
    _own_login()
    r = funding.select("pwm")
    assert r.route == funding.PWM and r.explicit
    funding.clear()
    assert funding.resolve().route == funding.OWN


def test_env_beats_the_saved_selection(clean, monkeypatch):
    funding.select("pwm")
    monkeypatch.setenv("AI4SCIENCE_FUNDING", "own")
    assert funding.resolve().route == funding.OWN
    monkeypatch.setenv("AI4SCIENCE_FUNDING", "pwm")
    assert funding.resolve().route == funding.PWM


def test_legacy_gate_switch_selects_pwm(clean, monkeypatch):
    _own_login()
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "1")
    r = funding.resolve()
    assert r.route == funding.PWM and r.explicit


def test_select_rejects_unknown_routes(clean):
    with pytest.raises(ValueError):
        funding.select("free-for-all")


# ── login is authentication, not a spending decision ─────────────────

def test_pwm_login_with_own_llm_changes_nothing(clean):
    _own_login()
    _pwm_login()
    note = funding.after_pwm_login()
    assert "own LLM stays" in note
    assert funding.resolve().route == funding.OWN


def test_pwm_login_with_nothing_else_selects_pwm_and_says_so(clean):
    _pwm_login()
    note = funding.after_pwm_login()
    assert "PWM-funded" in note
    assert funding.resolve().route == funding.PWM


def test_pwm_login_leaves_an_explicit_choice_alone(clean):
    funding.select("own")
    _pwm_login()
    assert funding.after_pwm_login() is None
    assert funding.resolve().route == funding.OWN


def test_own_llm_login_clears_a_stale_pwm_selection(clean, monkeypatch):
    from ai4science.commands import login
    funding.select("pwm")
    shown = []
    monkeypatch.setattr(login, "console", type("C", (), {"print": lambda self, *a, **k: shown.append(" ".join(map(str, a)))})())
    monkeypatch.setattr(login, "_reachable", lambda *a: None)
    login._finish_own("anthropic", "subscription", None)
    text = "\n".join(shown)
    assert "0 PWM" in text and "fee" in text and "10%" not in text
    assert funding.resolve().route == funding.OWN


# ── the adapter factory never pays on the free route ─────────────────

def test_own_route_never_returns_the_proxy(clean, monkeypatch):
    from ai4science.harness.adapters import factory
    from ai4science.harness.adapters.proxy import ProxyAdapter
    _own_login()
    _pwm_login()          # a token is remembered — it must not matter
    a = factory.adapter_for("gemini")      # no gemini credential here
    assert not isinstance(a, ProxyAdapter)
    assert factory.harness_available("gemini") is False


def test_pwm_route_serves_through_the_proxy(clean):
    from ai4science.harness.adapters import factory
    from ai4science.harness.adapters.proxy import ProxyAdapter
    _pwm_login()
    a = factory.adapter_for("gemini")
    assert isinstance(a, ProxyAdapter) and a.token == "pwm_t"
    assert a.base == "https://x.example"
    assert factory.harness_available("gemini") is True


def test_pwm_route_without_a_login_is_an_error_not_a_free_turn(clean, monkeypatch):
    from ai4science.harness.adapters import factory
    monkeypatch.setenv("AI4SCIENCE_FUNDING", "pwm")
    with pytest.raises(RuntimeError, match="no PWM login"):
        factory.adapter_for("gemini")


def test_pwm_route_ignores_the_users_own_key_and_says_so(clean, monkeypatch, capsys):
    """Routes don't mix: with PWM selected, a turn is never served on the
    user's own key (which would bill them twice — the provider AND PWM). The
    own key is ignored for the turn, with one line saying so."""
    from ai4science.harness.adapters import factory, creds
    from ai4science.harness.adapters.proxy import ProxyAdapter
    monkeypatch.setattr(creds, "available", lambda b: b == "anthropic")
    monkeypatch.setenv("AI4SCIENCE_FUNDING", "pwm")
    _pwm_login()
    assert isinstance(factory.adapter_for("anthropic"), ProxyAdapter)
    assert isinstance(factory.adapter_for("anthropic"), ProxyAdapter)
    notice = [l for l in capsys.readouterr().err.splitlines() if "own anthropic key" in l]
    assert len(notice) == 1 and "ai4science funding own" in notice[0]


def test_pwm_route_availability_is_the_proxy_not_a_local_key(clean, monkeypatch):
    from ai4science.harness.adapters import factory, creds
    monkeypatch.setattr(creds, "available", lambda b: b == "anthropic")
    monkeypatch.setenv("AI4SCIENCE_FUNDING", "pwm")
    assert factory.harness_available("anthropic") is False     # no PWM login
    _pwm_login()
    assert factory.harness_available("anthropic") is True


# ── the gate ─────────────────────────────────────────────────────────

def test_gate_is_off_on_the_free_route_even_when_logged_in(clean):
    from ai4science.harness.pwm_gate import PwmGate
    _own_login()
    _pwm_login()
    g = PwmGate.from_env()
    assert g.enabled is False
    assert g.check() == (True, "")          # no balance read, no block


def test_gate_is_on_when_pwm_is_the_only_credential(clean):
    from ai4science.harness.pwm_gate import PwmGate
    _pwm_login()
    assert PwmGate.from_env().enabled is True


def test_gate_is_on_when_pwm_is_selected(clean):
    from ai4science.harness.pwm_gate import PwmGate
    _own_login()
    _pwm_login()
    funding.select("pwm")
    assert PwmGate.from_env().enabled is True


def test_selected_paid_service_bills_on_the_free_route(clean):
    """A priced plug-in the user picked is authorized by that pick, not by
    the LLM's funding route — and still needs a token."""
    from ai4science.harness.pwm_gate import PwmGate
    _own_login()
    assert PwmGate.for_selected_service().enabled is False     # no token
    _pwm_login()
    assert PwmGate.for_selected_service().enabled is True
    assert PwmGate.from_env().enabled is False                 # the LLM stays free


def test_selected_service_respects_the_explicit_opt_out(clean, monkeypatch):
    from ai4science.harness.pwm_gate import PwmGate
    _pwm_login()
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "0")
    assert PwmGate.for_selected_service().enabled is False


# ── chat does not ask a free user to sign in ─────────────────────────

def test_chat_does_not_offer_login_on_the_free_route(clean, monkeypatch):
    from ai4science.commands import chat
    _own_login()
    shown = []
    monkeypatch.setattr(chat, "console", type("C", (), {"print": lambda self, *a, **k: shown.append(" ".join(map(str, a)))})())
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("asked")))
    chat._maybe_offer_login()
    assert shown == []


def test_chat_still_offers_login_when_pwm_is_selected_without_a_token(clean, monkeypatch):
    from ai4science.commands import chat
    monkeypatch.setenv("AI4SCIENCE_FUNDING", "pwm")
    shown = []
    monkeypatch.setattr(chat, "console", type("C", (), {"print": lambda self, *a, **k: shown.append(" ".join(map(str, a)))})())
    monkeypatch.setattr("builtins.input", lambda *a: "n")
    chat._maybe_offer_login()
    assert any("not signed in" in s for s in shown)


# ── a turn is charged once, by whoever served it ─────────────────────

class _FakeGatewayStream:
    """What the platform proxy streams back: its receipt, the gateway's text
    and usage events (forwarded), done. The platform has already charged."""
    status_code = 200
    LINES = ['{"t": "receipt", "request_id": "r1", "status": "dispatched"}',
             '{"t": "text", "text": "hi"}',
             '{"t": "usage", "input": 1000, "output": 500, "total": 1500}',
             '{"t": "done", "stop_reason": "end_turn"}']

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        return iter(self.LINES)

    def close(self):
        pass


def test_a_proxied_turn_is_not_charged_again_by_the_client(clean, monkeypatch):
    """The platform proxy charges the turn server-side. The client must not
    price the forwarded usage and POST /spend for the same turn."""
    import httpx
    from ai4science.harness import repl as repl_mod
    from ai4science.harness.pwm_gate import PwmGate
    _pwm_login()
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeGatewayStream())
    monkeypatch.setattr(repl_mod.routing, "_select_source",
                        lambda backend: ("src", "pid", "0xWALLET", 1.0))
    monkeypatch.setattr(repl_mod.pricing, "price_call",
                        lambda model, usage, price_multiplier=1.0: {"pwm": 0.5, "usd": 0.1})
    charged = []

    def _charge(self, amount, wallet, **kw):
        charged.append(amount)
        return True, ""
    monkeypatch.setattr(PwmGate, "charge", _charge)
    monkeypatch.setattr(PwmGate, "check", lambda self, *a, **k: (True, ""))
    inputs = iter(["hello"])

    def _input(*a, **k):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError()
    monkeypatch.setattr("builtins.input", _input)
    repl_mod.run_common_repl(clean, backend="anthropic", model="claude-sonnet-5")
    assert charged, "the turn never reached the charge step"
    assert all(a == 0 for a in charged), f"client charged {charged} on top of the platform"
