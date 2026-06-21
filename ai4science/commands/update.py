"""`ai4science update` — self-upgrade in one word, like `claude update`.

Channel-aware (Part A): re-installs the latest build of the user's CHANNEL —
stable (default) | rc | dev — each mapped to a GitHub branch ZIP. The channel is
remembered in ``$AI4SCIENCE_HOME/channel`` (written by install.sh); pass
``--stable``/``--rc``/``--dev`` to switch lines (rewrites that file).

Figures out the right pip invocation for THIS install:
  • inside a venv      → plain pip into the venv
  • pipx               → `pipx install --force`
  • PEP 668 system py   → `pip --user --break-system-packages`
  • plain system py     → `pip --user`

Always --force-reinstall --no-cache-dir: pip caches the GitHub zip by URL, so
without them an "upgrade" silently reinstalls the stale build.
"""
from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Optional

import typer

PKG = "pwm-ai4science[claude]"
_GH = "https://github.com/integritynoble/AI4Science/archive/refs/heads"
_GH_SHA = "https://github.com/integritynoble/AI4Science/archive"
_API = "https://api.github.com/repos/integritynoble/AI4Science/commits/main"
_BRANCH = {"stable": "stable", "rc": "rc", "dev": "main"}


def _dev_zip_url() -> str:
    """Cache-proof dev URL: resolve main's HEAD commit and use the IMMUTABLE
    per-commit archive (archive/<sha>.zip). GitHub caches the branch zip
    (archive/refs/heads/main.zip) for minutes after a push, so a fresh
    `update --dev` can otherwise reinstall stale code. Falls back to the branch
    zip if the commit can't be resolved (offline API, etc.)."""
    try:
        import json
        import urllib.request
        req = urllib.request.Request(
            _API, headers={"Accept": "application/vnd.github.sha",
                           "User-Agent": "ai4science-update"})
        with urllib.request.urlopen(req, timeout=15) as r:
            sha = r.read().decode("utf-8").strip()
        if sha and all(c in "0123456789abcdef" for c in sha.lower()):
            return f"{_GH_SHA}/{sha}.zip"
    except Exception:
        pass
    return f"{_GH}/main.zip"


def _home() -> Path:
    return Path(os.environ.get("AI4SCIENCE_HOME", Path.home() / ".ai4science"))


def _channel_file() -> Path:
    return _home() / "channel"


def read_channel() -> str:
    """The user's release channel (default stable). Env override for testing."""
    env = (os.environ.get("AI4SCIENCE_CHANNEL") or "").strip().lower()
    if env in _BRANCH:
        return env
    try:
        c = _channel_file().read_text(encoding="utf-8").strip().lower()
        if c in _BRANCH:
            return c
    except Exception:
        pass
    return "stable"


def write_channel(channel: str) -> None:
    try:
        _home().mkdir(parents=True, exist_ok=True)
        _channel_file().write_text(channel + "\n", encoding="utf-8")
    except Exception:
        pass


def _spec(channel: str) -> str:
    url = _dev_zip_url() if channel == "dev" else f"{_GH}/{_BRANCH[channel]}.zip"
    return f"{PKG} @ {url}"


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


def _pip_cmd(*specs: str, force: bool = True, no_deps: bool = False) -> list:
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir"]
    if force:
        cmd.append("--force-reinstall")
    if no_deps:
        cmd.append("--no-deps")
    if not _in_venv():
        cmd.append("--user")
        if _externally_managed():
            cmd.append("--break-system-packages")
    cmd.extend(specs)
    return cmd


def _install_one(tail: tuple) -> int:
    """Install one candidate in two phases to avoid the Windows [WinError 5]
    file-lock that --force-reinstall triggers on compiled deps (PyYAML/pyzmq
    .pyd files locked by the running interpreter):

      1. deps WITHOUT --force — pip skips already-satisfied compiled deps, so
         their locked .pyd files are never touched.
      2. our package WITH --force-reinstall --no-deps — pure-Python, overwrites
         only ai4science/pwm_core .py files (never locked), refreshing the code
         even when the version string is unchanged.

    Success is judged on phase 2 (the code refresh); phase 1 failures are
    non-fatal — if deps are already present, the code update still lands.
    """
    if _via_pipx():
        return subprocess.call(["pipx", "install", "--force", *tail])
    subprocess.call(_pip_cmd(*tail, force=False, no_deps=False))   # phase 1: deps
    return subprocess.call(_pip_cmd(*tail, force=True, no_deps=True))  # phase 2: code


def _candidates(channel: str) -> list:
    """Ordered (trailing-arg) lists to try: PyPI first for stable/rc (phase 2),
    then the GitHub branch zip. dev is GitHub-only."""
    if channel == "stable":
        return [(PKG,), (_spec("stable"),)]
    if channel == "rc":
        return [("--pre", PKG), (_spec("rc"),)]
    return [(_spec("dev"),)]


def update(
    stable: bool = typer.Option(False, "--stable", help="Switch to the stable channel and update."),
    rc: bool = typer.Option(False, "--rc", help="Switch to the rc (release-candidate) channel."),
    dev: bool = typer.Option(False, "--dev", help="Switch to the dev (main) channel."),
) -> None:
    """Upgrade ai4science to the latest build of your channel (stable by default)."""
    from ai4science import __version__
    switch = "stable" if stable else "rc" if rc else "dev" if dev else None
    channel = switch or read_channel()
    if switch:
        write_channel(switch)
        typer.echo(f"[update] switched to the [{switch}] channel")

    typer.echo(f"[update] current: {__version__}  ·  channel: {channel}")
    rc_code = 1
    cands = _candidates(channel)
    for i, tail in enumerate(cands):
        typer.echo(f"[update] installing {' '.join(tail)} …")
        rc_code = _install_one(tail)
        if rc_code == 0:
            break
        if i + 1 < len(cands):
            typer.echo("[update] that source failed; trying the next…")
    if rc_code != 0:
        # --no-deps avoids relocking compiled deps (the Windows [WinError 5] cause)
        typer.echo("[update] failed — see pip output above. Manual fallback "
                   "(skips deps, avoids the Windows file-lock):\n"
                   f"  pip install --user --force-reinstall --no-deps "
                   f"--no-cache-dir '{_spec(channel)}'")
        raise typer.Exit(rc_code)
    # report the NEW version from a fresh interpreter (this process still has the
    # old module loaded; importlib.metadata can hit a stale dist-info)
    out = subprocess.run(
        [sys.executable, "-c",
         "import ai4science, os; print(ai4science.__version__); "
         "print(os.path.dirname(ai4science.__file__))"],
        capture_output=True, text=True)
    parts = (out.stdout or "").strip().splitlines()
    new = parts[0].strip() if parts else "?"
    loc = parts[1].strip() if len(parts) > 1 else ""
    typer.echo(f"[update] done — now at {new} ([{channel}]). "
               "Restart any running `ai4science chat` sessions to pick it up.")
    if loc:
        typer.echo(f"[update] installed into: {loc}")
    _warn_if_shadowed(new)


def _warn_if_shadowed(new_version: str) -> None:
    """If the `ai4science` on PATH is a DIFFERENT install than the one we just
    updated, the user keeps running stale code no matter how often they update.
    Detect it and say so loudly with the exact fix — this is the usual reason an
    update 'doesn't take' (e.g. an old pip --user install shadowing the venv)."""
    import shutil
    launcher = shutil.which("ai4science")
    if not launcher:
        return
    try:
        lout = subprocess.run([launcher, "version"], capture_output=True,
                              text=True, timeout=30)
        lver = (lout.stdout or "").strip()
    except Exception:
        return
    if new_version != "?" and new_version not in lver:
        typer.echo(
            f"\n[update] ⚠ PATH MISMATCH — this is why your update isn't taking:\n"
            f"    `ai4science` on your PATH is {launcher}\n"
            f"    it reports: {lver or '(unknown)'}  (NOT {new_version})\n"
            f"    A different install is shadowing the one just updated.\n"
            f"    Fix: run the updated one directly to confirm —\n"
            f"      {sys.prefix}/bin/ai4science version\n"
            f"    then remove/relink the stale launcher, or reinstall with the "
            f"official installer so PATH points at this env.")
