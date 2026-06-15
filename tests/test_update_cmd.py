"""`ai4science update` picks the right pip invocation + is channel-aware (Part A)."""
import os
from ai4science.commands import update as u

SPEC = u._spec("stable")


def test_pip_cmd_venv_is_plain(monkeypatch):
    monkeypatch.setattr(u, "_in_venv", lambda: True)
    cmd = u._pip_cmd(SPEC)
    assert "--user" not in cmd and "--break-system-packages" not in cmd
    assert "--force-reinstall" in cmd and "--no-cache-dir" in cmd
    assert cmd[-1] == SPEC


def test_pip_cmd_debian_system_python(monkeypatch):
    # PEP 668 externally-managed host (e.g. agent-prod) → --user + override
    monkeypatch.setattr(u, "_in_venv", lambda: False)
    monkeypatch.setattr(u, "_externally_managed", lambda: True)
    cmd = u._pip_cmd(SPEC)
    assert "--user" in cmd and "--break-system-packages" in cmd


def test_pip_cmd_plain_system_python(monkeypatch):
    monkeypatch.setattr(u, "_in_venv", lambda: False)
    monkeypatch.setattr(u, "_externally_managed", lambda: False)
    cmd = u._pip_cmd(SPEC)
    assert "--user" in cmd and "--break-system-packages" not in cmd


# ── channels (Part A) ────────────────────────────────────────────────────────
def test_channel_default_is_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_HOME", str(tmp_path))
    monkeypatch.delenv("AI4SCIENCE_CHANNEL", raising=False)
    assert u.read_channel() == "stable"


def test_channel_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_HOME", str(tmp_path))
    monkeypatch.delenv("AI4SCIENCE_CHANNEL", raising=False)
    u.write_channel("rc")
    assert u.read_channel() == "rc"


def test_channel_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_HOME", str(tmp_path))
    u.write_channel("stable")
    monkeypatch.setenv("AI4SCIENCE_CHANNEL", "dev")
    assert u.read_channel() == "dev"


def test_spec_maps_channel_to_branch():
    assert u._spec("stable").endswith("/stable.zip")
    assert u._spec("rc").endswith("/rc.zip")
    assert u._spec("dev").endswith("/main.zip")
