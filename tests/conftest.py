"""Shared test isolation.

The PWM gate now turns ON automatically when an `ai4science login` account is
remembered on disk. Tests must NOT depend on whether the machine running them
happens to be logged in — point the account file at a nonexistent path and
clear the PWM env so the gate is OFF by default. Tests that exercise PWM set
`PWM_TOKEN` / `AI4SCIENCE_PWM_GATE` (and may override the account path)
themselves; monkeypatch applied in the test body wins over this autouse
fixture and restores cleanly.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_pwm_login(monkeypatch, tmp_path_factory):
    missing = tmp_path_factory.mktemp("pwm_isolate") / "no_account.json"
    monkeypatch.setenv("AI4SCIENCE_PWM_ACCOUNT", str(missing))
    for k in ("PWM_TOKEN", "PWM_ONBOARD_TOKEN", "PWM_BASE",
              "PWM_ONBOARD_BASE", "AI4SCIENCE_PWM_GATE"):
        monkeypatch.delenv(k, raising=False)
    yield
