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


@pytest.fixture(autouse=True)
def _restore_agent_registry():
    """Put the global agent registry back exactly as it was, for every test.

    Three files carried their own version of this, and all three did it by
    calling `registry.reload()` at teardown — which RE-DISCOVERS through
    whatever `monkeypatch` is still faking. Fixture finalizers run in reverse
    setup order, so when the restore fixture happened to be set up first, its
    teardown ran while `_iter_entry_points` was still patched, and the global
    registry was left holding only the test's fake specs.

    Measured: `test_ai4sci_mode_alias.py` installs a fake spec named `ai4sci`,
    and afterwards `registry.get("research")` returned None for the rest of the
    session — so `ai4science chat --mode research` fell back to the unified
    spec and three tests in `test_chat.py` failed, in a file that passes on its
    own, about a package they never touch.

    Restoring the CONTENTS is order-independent: it needs no discovery, so
    nothing it depends on can still be mocked when it runs.
    """
    from ai4science.harness.agents import registry as _reg
    saved_specs = dict(_reg.AGENT_REGISTRY)
    saved_aliases = dict(_reg.AGENT_ALIASES)
    yield
    if (_reg.AGENT_REGISTRY != saved_specs
            or _reg.AGENT_ALIASES != saved_aliases):
        _reg.AGENT_REGISTRY.clear()
        _reg.AGENT_REGISTRY.update(saved_specs)
        _reg.AGENT_ALIASES.clear()
        _reg.AGENT_ALIASES.update(saved_aliases)
