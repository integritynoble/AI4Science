"""`ai4science update` — self-upgrade in one word, like `claude update`.

Re-installs the latest build from GitHub main, figuring out the right pip
invocation for THIS install so the user never has to remember flags:

  • inside a venv            → plain pip into the venv
  • installed via pipx       → `pipx install --force`
  • system python (Debian PEP 668 "externally-managed-environment")
                             → `pip --user --break-system-packages`
  • plain system python      → `pip --user`

Always passes --force-reinstall --no-cache-dir: pip caches the GitHub zip by
URL, so without them an "upgrade" silently reinstalls the stale build.
"""
from __future__ import annotations

import subprocess
import sys
import sysconfig
from pathlib import Path

import typer

SPEC = ("pwm-ai4science[claude] @ "
        "https://github.com/integritynoble/AI4Science/archive/refs/heads/main.zip")


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _via_pipx() -> bool:
    return "pipx" in str(Path(sys.executable).resolve()).split("/")


def _externally_managed() -> bool:
    """Debian/Ubuntu PEP 668 marker on the system interpreter."""
    try:
        return (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").exists()
    except Exception:
        return False


def _pip_cmd() -> list:
    cmd = [sys.executable, "-m", "pip", "install",
           "--force-reinstall", "--no-cache-dir"]
    if not _in_venv():
        cmd.append("--user")
        if _externally_managed():
            cmd.append("--break-system-packages")
    cmd.append(SPEC)
    return cmd


def update() -> None:
    """Upgrade ai4science to the latest build (one word, no flags)."""
    from ai4science import __version__
    typer.echo(f"[update] current version: {__version__}")
    if _via_pipx():
        cmd = ["pipx", "install", "--force", SPEC]
    else:
        cmd = _pip_cmd()
    typer.echo(f"[update] running: {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc != 0:
        typer.echo("[update] failed — see pip output above. Manual fallback:\n"
                   f"  pip install --user --break-system-packages "
                   f"--force-reinstall --no-cache-dir '{SPEC}'")
        raise typer.Exit(rc)
    # report the NEW version from a fresh interpreter (this process still has
    # the old module loaded)
    out = subprocess.run(
        [sys.executable, "-c",
         "import ai4science; print(ai4science.__version__)"],
        capture_output=True, text=True)  # same source `ai4science version` uses
        # (importlib.metadata can hit a stale dist-info shadowing the install)
    new = (out.stdout or "").strip() or "?"
    typer.echo(f"[update] done — now at {new}. "
               "Restart any running `ai4science chat` sessions to pick it up.")
