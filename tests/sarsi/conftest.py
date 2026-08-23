"""Sarsi test isolation.

`session.assign` refuses a spec that is not installed, and discovers what IS
installed by reading the real `AGENT_REGISTRY` — which depends on what agent
packages the machine running the tests happens to have. `unified-LLM` (the
sarsi-ai4sci default engine) ships as `pwm-agent-unified` and is NOT a built-in
spec, so on a machine without it every `assign` of a default-backend task
raises `SpecUnavailable` — and whether a given test passed depended on which
earlier test had left the registry populated.

Same doctrine as `tests/conftest.py`'s PWM-login isolation and this tree's
`live=` injection: the machine must not walk into the assertions. An empty
set skips the availability check (the same idiom as the many call sites that
pass `installed=lambda: set()`); a test that exercises refusal passes its own
non-empty `installed=`, which takes precedence over this default.
"""
import pytest

from ai4science.harness.agents.sarsi import session as ses


@pytest.fixture(autouse=True)
def _hermetic_installed_specs(monkeypatch):
    monkeypatch.setattr(ses, "installed_specs", lambda: set())


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch):
    """The chat door may call a model; the suite must not.

    Same doctrine as the registry isolation above. Whether an API key happens
    to be configured on the machine running the tests is not a property of the
    code under test, and a suite that reaches the network measures the network.
    A test that WANTS generation injects its own callable.
    """
    monkeypatch.setenv("SARSI_CHAT_LLM", "0")


@pytest.fixture(autouse=True)
def _verifier_baseline_intact():
    """Restore the import-time verifier baseline after every test.

    An empty baseline is a refusal — `_check_verifier_integrity` will not adopt
    whatever happens to be on disk — so a test that clears it and does not put
    it back makes every LATER test reject every phase. That is exactly what
    happened: one `clear()` with no restore cost seventeen failures in files
    that pass on their own, and the symptom (a task stuck at `running`) points
    nowhere near the cause.
    """
    from ai4science.harness.agents.sarsi import session as _ses
    saved = dict(_ses._VERIFIER_BASELINE)
    yield
    _ses._VERIFIER_BASELINE.clear()
    _ses._VERIFIER_BASELINE.update(saved or _ses.verifier_hashes())
