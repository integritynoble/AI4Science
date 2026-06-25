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
    # dev resolves to an immutable per-commit archive URL (SHA or branch fallback)
    dev_spec = u._spec("dev")
    assert "integritynoble/AI4Science/archive" in dev_spec and dev_spec.endswith(".zip")


# ── Windows self-update deadlock (overlay) ────────────────────────────────────

def test_install_one_uses_overlay_on_windows(monkeypatch):
    # On Windows phase-2 must go through _overlay_install (never rewrites the
    # locked ai4science.exe), NOT pip --force-reinstall.
    monkeypatch.setattr(u.sys, "platform", "win32")
    monkeypatch.setattr(u, "_via_pipx", lambda: False)
    monkeypatch.setattr(u.subprocess, "call", lambda *a, **k: 0)  # phase-1 deps
    called = {}
    def fake_overlay(tail):
        called["tail"] = tail
        return 0
    monkeypatch.setattr(u, "_overlay_install", fake_overlay)
    rc = u._install_one(("pkg @ url",))
    assert rc == 0 and called["tail"] == ("pkg @ url",)


def test_install_one_uses_pip_force_off_windows(monkeypatch):
    monkeypatch.setattr(u.sys, "platform", "linux")
    monkeypatch.setattr(u, "_via_pipx", lambda: False)
    seen = []
    monkeypatch.setattr(u.subprocess, "call", lambda cmd, *a, **k: seen.append(cmd) or 0)
    monkeypatch.setattr(u, "_overlay_install",
                        lambda tail: (_ for _ in ()).throw(AssertionError("overlay on linux")))
    rc = u._install_one(("pkg @ url",))
    assert rc == 0
    # phase 2 (last call) is a pip --force-reinstall --no-deps invocation
    assert "--force-reinstall" in seen[-1] and "--no-deps" in seen[-1]


def test_overlay_copies_package_trees(monkeypatch, tmp_path):
    # _overlay_install copies ai4science + pwm_core from the pip --target dir
    # over the live install, refreshing .py without touching any launcher.
    import ai4science
    site = tmp_path / "site"
    (site / "ai4science").mkdir(parents=True)
    (site / "ai4science" / "__init__.py").write_text('__version__ = "OLD"\n')
    monkeypatch.setattr(ai4science, "__file__", str(site / "ai4science" / "__init__.py"))

    def fake_pip(cmd, *a, **k):
        tgt = __import__("pathlib").Path(cmd[cmd.index("--target") + 1])
        (tgt / "ai4science").mkdir(parents=True, exist_ok=True)
        (tgt / "ai4science" / "__init__.py").write_text('__version__ = "NEW"\n')
        return 0
    monkeypatch.setattr(u.subprocess, "call", fake_pip)

    rc = u._overlay_install(("pwm-ai4science @ url",))
    assert rc == 0
    assert 'NEW' in (site / "ai4science" / "__init__.py").read_text()
