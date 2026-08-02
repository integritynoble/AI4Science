"""`~/.sarsi` is a SEPARATE state root from ai4science's own.

The design couples sarsi to ai4science as a *library*, not as a *system*: it may
import the machine agent's session control, and it may not share its store. So
the resolver must never fall back to the control-plane state dir.
"""
from pathlib import Path

import ai4science.harness.agents.sarsi.state as st


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    assert st.state_dir() == tmp_path


def test_default_is_dot_sarsi_under_home(monkeypatch):
    monkeypatch.delenv("SARSI_STATE_DIR", raising=False)
    assert st.state_dir() == Path.home() / ".sarsi"


def test_never_falls_back_to_the_ai4science_state_dir(monkeypatch):
    """PWM_CP_STATE_DIR points at the machine agent's store. Sharing it would
    put sarsi's registry, ledgers and vault in ai4science's directory."""
    monkeypatch.delenv("SARSI_STATE_DIR", raising=False)
    monkeypatch.setenv("PWM_CP_STATE_DIR", "/tmp/somewhere-else")
    assert st.state_dir() != Path("/tmp/somewhere-else")


def test_fallback_stays_per_user_when_home_unresolvable(monkeypatch):
    monkeypatch.delenv("SARSI_STATE_DIR", raising=False)

    def boom():
        raise RuntimeError("no home")
    monkeypatch.setattr(st.Path, "home", staticmethod(boom))
    d = st.state_dir()
    assert d.name.startswith("sarsi-")          # keyed by user/uid, never world-shared
    assert d != Path("/tmp/sarsi")
