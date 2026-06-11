"""`ai4science login --pwm` — account store, device flow, and gate fallback.

The stored credential is a revocable pwm_ API key — these tests pin the
invariants: token-only storage (0600), env always wins, one-time flow states.
"""
import json
import os
import stat

import pytest

from ai4science import pwm_account


@pytest.fixture()
def store(tmp_path, monkeypatch):
    p = tmp_path / "pwm_account.json"
    monkeypatch.setenv("AI4SCIENCE_PWM_ACCOUNT", str(p))
    return p


def test_save_load_roundtrip_and_0600(store):
    pwm_account.save(base="https://x.example/", token="pwm_abc",
                     email="a@b.c", wallet="0x" + "1" * 40, user_id=7)
    acct = pwm_account.load()
    assert acct["token"] == "pwm_abc"
    assert acct["base"] == "https://x.example"          # trailing slash stripped
    assert acct["email"] == "a@b.c" and acct["user_id"] == 7
    mode = stat.S_IMODE(os.stat(store).st_mode)
    assert mode == 0o600, f"account file must be 0600, got {oct(mode)}"


def test_load_none_when_missing_or_tokenless(store):
    assert pwm_account.load() is None
    store.write_text(json.dumps({"base": "https://x", "token": ""}))
    assert pwm_account.load() is None


def test_clear(store):
    pwm_account.save(base="https://x", token="pwm_abc")
    assert pwm_account.clear() is True
    assert pwm_account.load() is None
    assert pwm_account.clear() is False


def _flow_responses(monkeypatch, polls):
    """Mock httpx.post: first call = start, then successive poll bodies."""
    calls = {"n": 0}

    class _Resp:
        def __init__(self, d):
            self._d = d
        def raise_for_status(self):
            pass
        def json(self):
            return self._d

    def fake_post(url, **kw):
        if url.endswith("/start"):
            return _Resp({"device_code": "dev123", "user_code": "ABCD-2345",
                          "verification_url": "https://x/cli-auth?code=ABCD-2345",
                          "interval": 0, "expires_in": 30})
        body = polls[min(calls["n"], len(polls) - 1)]
        calls["n"] += 1
        return _Resp(body)

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)


def test_device_flow_approved_saves_token(store, monkeypatch):
    _flow_responses(monkeypatch, [
        {"status": "pending"},
        {"status": "approved", "token": "pwm_devflow", "email": "u@x.c",
         "wallet": "0x" + "2" * 40, "user_id": 3},
    ])
    acct = pwm_account.login_device_flow("https://x", echo=lambda *_: None,
                                         sleeper=lambda _s: None, open_browser=False)
    assert acct["token"] == "pwm_devflow" and acct["email"] == "u@x.c"
    assert pwm_account.load()["token"] == "pwm_devflow"


def test_device_flow_denied_raises(store, monkeypatch):
    _flow_responses(monkeypatch, [{"status": "denied"}])
    with pytest.raises(RuntimeError, match="denied"):
        pwm_account.login_device_flow("https://x", echo=lambda *_: None,
                                      sleeper=lambda _s: None, open_browser=False)
    assert pwm_account.load() is None


def test_device_flow_expired_raises(store, monkeypatch):
    _flow_responses(monkeypatch, [{"status": "expired"}])
    with pytest.raises(RuntimeError, match="expired"):
        pwm_account.login_device_flow("https://x", echo=lambda *_: None,
                                      sleeper=lambda _s: None, open_browser=False)


def test_gate_uses_stored_account(store, monkeypatch):
    from ai4science.harness.pwm_gate import PwmGate
    for v in ("PWM_TOKEN", "PWM_ONBOARD_TOKEN", "PWM_BASE", "PWM_ONBOARD_BASE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "1")
    pwm_account.save(base="https://stored.example", token="pwm_stored")
    g = PwmGate.from_env()
    assert g.enabled and g.token == "pwm_stored" and g.base == "https://stored.example"


def test_env_token_beats_stored_account(store, monkeypatch):
    from ai4science.harness.pwm_gate import PwmGate
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "1")
    monkeypatch.setenv("PWM_TOKEN", "pwm_env")
    monkeypatch.delenv("PWM_BASE", raising=False)
    monkeypatch.delenv("PWM_ONBOARD_BASE", raising=False)
    pwm_account.save(base="https://stored.example", token="pwm_stored")
    g = PwmGate.from_env()
    assert g.token == "pwm_env"
    assert g.base == "https://physicsworldmodel.org"   # env token → env/default base


def test_gate_disabled_without_any_token(store, monkeypatch):
    from ai4science.harness.pwm_gate import PwmGate
    for v in ("PWM_TOKEN", "PWM_ONBOARD_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "1")
    assert PwmGate.from_env().enabled is False


def test_login_falls_back_to_published_mirror(store, monkeypatch):
    calls = []

    class _Resp:
        def __init__(self, code, data=None, text=""):
            self.status_code = code; self._d = data; self.text = text
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")
        def json(self):
            return self._d

    def fake_post(url, **kw):
        calls.append(url)
        if url.startswith("https://physicsworldmodel.org"):
            return _Resp(403)                       # institutional block
        if "/start" in url:
            return _Resp(200, {"device_code": "d", "user_code": "AAAA-1111",
                               "verification_url": "https://mirror.example/cli-auth?code=AAAA-1111",
                               "interval": 0, "expires_in": 5})
        return _Resp(200, {"status": "approved", "token": "pwm_mirrored",
                           "user_id": 9})

    def fake_get(url, **kw):
        assert "MIRROR.url" in url
        return _Resp(200, text="https://mirror.example\n")

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    acct = pwm_account.login_device_flow(echo=lambda *_: None,
                                         sleeper=lambda _s: None, open_browser=False)
    assert acct["token"] == "pwm_mirrored"
    assert acct["base"] == "https://mirror.example"   # stored → gate uses mirror too
    assert any(u.startswith("https://mirror.example") for u in calls)
