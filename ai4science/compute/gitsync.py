"""Git-synced inbox helpers.

When the dispatcher (CPU box) and the provider (GPU box) are different
machines, the file-inbox is shared through a git repo: the dispatcher
commits + pushes job requests; the provider pulls them, runs, commits +
pushes results; the dispatcher pulls to verify.

These helpers are deliberately defensive — a transient git failure
(offline, push race) logs a warning but never crashes the poller. All
operations are scoped to the repo containing the inbox directory.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def _git(repo: Path, *args: str, timeout: int = 120) -> Tuple[int, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return out.returncode, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, f"{type(e).__name__}: {e}"


def find_repo_root(path: Path) -> Optional[Path]:
    """Return the git work-tree root containing *path*, or None."""
    p = Path(path).expanduser().resolve()
    start = p if p.is_dir() else p.parent
    rc, out = _git(start, "rev-parse", "--show-toplevel", timeout=15)
    return Path(out) if rc == 0 and out else None


def pull(repo: Path) -> Tuple[bool, str]:
    """git pull --rebase --autostash (bring in the other side's commits)."""
    rc, out = _git(repo, "pull", "--rebase", "--autostash")
    return rc == 0, out


def commit_push(repo: Path, paths: List[Path], message: str) -> Tuple[bool, str]:
    """Stage *paths*, commit, rebase-pull, and push. No-op if nothing changed."""
    for p in paths:
        _git(repo, "add", str(p), timeout=30)
    # Anything staged?
    rc_diff, _ = _git(repo, "diff", "--cached", "--quiet", timeout=30)
    if rc_diff == 0:
        return True, "nothing to commit"
    rc_c, out_c = _git(repo, "commit", "-m", message, timeout=30)
    if rc_c != 0:
        return False, f"commit failed: {out_c}"
    # Reduce push races by rebasing on remote first.
    _git(repo, "pull", "--rebase", "--autostash")
    rc_p, out_p = _git(repo, "push")
    return rc_p == 0, out_p
