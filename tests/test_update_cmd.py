"""`ai4science update` picks the right pip invocation for the install style."""
from ai4science.commands import update as u


def test_pip_cmd_venv_is_plain(monkeypatch):
    monkeypatch.setattr(u, "_in_venv", lambda: True)
    cmd = u._pip_cmd()
    assert "--user" not in cmd and "--break-system-packages" not in cmd
    assert "--force-reinstall" in cmd and "--no-cache-dir" in cmd
    assert cmd[-1] == u.SPEC


def test_pip_cmd_debian_system_python(monkeypatch):
    # PEP 668 externally-managed host (e.g. agent-prod) → --user + override
    monkeypatch.setattr(u, "_in_venv", lambda: False)
    monkeypatch.setattr(u, "_externally_managed", lambda: True)
    cmd = u._pip_cmd()
    assert "--user" in cmd and "--break-system-packages" in cmd


def test_pip_cmd_plain_system_python(monkeypatch):
    monkeypatch.setattr(u, "_in_venv", lambda: False)
    monkeypatch.setattr(u, "_externally_managed", lambda: False)
    cmd = u._pip_cmd()
    assert "--user" in cmd and "--break-system-packages" not in cmd
