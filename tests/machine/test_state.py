from pathlib import Path

import ai4science.harness.agents.machine.state as st


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    assert st.state_dir() == tmp_path


def test_per_user_default_not_world_shared_tmp(monkeypatch):
    monkeypatch.delenv("PWM_CP_STATE_DIR", raising=False)
    d = st.state_dir()
    assert d == Path.home() / ".local" / "share" / "pwm-cp"
    assert not str(d).startswith("/tmp")            # never a world-shared /tmp path


def test_fallback_stays_per_user_when_home_unresolvable(monkeypatch):
    monkeypatch.delenv("PWM_CP_STATE_DIR", raising=False)

    def boom():
        raise RuntimeError("no home")
    monkeypatch.setattr(st.Path, "home", staticmethod(boom))
    d = st.state_dir()
    assert d.name.startswith("pwm-cp-")             # keyed by user/uid, not a shared bare dir
