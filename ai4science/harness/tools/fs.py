from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path

# Heavy / noise dirs pruned from name + content search (like Claude Code's
# defaults). Keeps scoped searches fast and the output readable.
_PRUNE = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache", ".tox",
    ".next", "dist", "build", "site-packages", ".idea", ".gradle",
}

# Roots too broad to ever search: '/' and kernel pseudo-dirs would burn the
# whole time budget on /proc, /sys, … and return nothing useful. Anthropic's
# Glob/Grep stay in the project — mirror that and redirect instead of hanging.
_BROAD_ROOTS = {"/", "/proc", "/sys", "/dev", "/run", "/var/run"}


def _too_broad(root: Path) -> str | None:
    if str(root) in _BROAD_ROOTS:
        return (f"[refused] '{root}' is too broad to search — it would scan the "
                f"whole machine and time out. Search the project workspace "
                f"(omit `path`), or pass a specific subdirectory.")
    return None


def _root(workspace: Path, path: str | None) -> Path:
    """Resolve a search root: absolute paths as-is (so the model can search the
    whole machine, e.g. '/home/user' or '/'), relative paths under the
    workspace. Defaults to the workspace."""
    if not path:
        return Path(workspace)
    p = Path(path).expanduser()
    return p if p.is_absolute() else (Path(workspace) / p)


def read(workspace: Path, *, path: str) -> str:
    p = (Path(workspace) / path)
    text = p.read_text()
    lines = text.splitlines()
    return "\n".join(f"{i+1}\t{ln}" for i, ln in enumerate(lines))


def write(workspace: Path, *, path: str, content: str) -> str:
    p = (Path(workspace) / path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} bytes to {path}"


def edit(workspace: Path, *, path: str, old: str, new: str) -> str:
    p = (Path(workspace) / path)
    text = p.read_text()
    count = text.count(old)
    if count == 0:
        raise ValueError(f"old string not found in {path}")
    if count > 1:
        raise ValueError(f"old string is not unique in {path} ({count} matches)")
    p.write_text(text.replace(old, new, 1))
    return f"edited {path}"


def glob(workspace: Path, *, pattern: str, path: str | None = None,
         limit: int = 1000, time_budget: float = 20.0) -> str:
    """Find files AND folders whose name (or path under the root) matches the
    glob `pattern`, fast, pruning heavy dirs. `path` sets the root (default:
    workspace); use an absolute path to search anywhere on the machine.

    Returns absolute paths, one per line, directories suffixed with '/'."""
    root = _root(workspace, path)
    broad = _too_broad(root)
    if broad:
        return broad
    # A degenerate pattern ('/' or empty) matches nothing but still scans the
    # whole root for the full budget. Treat it as 'list everything', like
    # Anthropic's '**/*', so the model gets results instead of a 20s 0-hit note.
    if not pattern or not pattern.strip("/ *"):
        pattern = "*"

    def _match(name: str, rel: str) -> bool:
        return fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern)

    find = shutil.which("find")
    if find:
        # `find` matches names regardless of .gitignore (the global ~/.config/
        # git/ignore makes ripgrep blind here) and returns folders too. Pruned
        # for speed and STREAMED under a wall-clock budget so a huge tree never
        # hangs — partial results + a note instead, like a responsive tool.
        prune: list[str] = []
        for d in sorted(_PRUNE):
            prune += ["-name", d, "-o"]
        prune = prune[:-1]
        flag = "-ipath" if "/" in pattern else "-iname"
        needle = pattern if flag == "-iname" else (
            pattern if pattern.startswith("*") else f"*{pattern}")
        cmd = [find, str(root), "(", *prune, ")", "-prune", "-o", flag, needle, "-print"]
        try:
            import select
            import time as _time
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
            paths: list[str] = []
            truncated = False
            deadline = _time.monotonic() + time_budget
            buf = b""
            while True:
                if _time.monotonic() > deadline:
                    truncated = True; proc.kill(); break
                r, _w, _e = select.select([proc.stdout], [], [], 0.5)
                if r:
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line:
                            paths.append(line.decode("utf-8", "replace"))
                    if len(paths) >= limit:
                        truncated = True; proc.kill(); break
                elif proc.poll() is not None:
                    break
            for line in buf.split(b"\n"):
                if line:
                    paths.append(line.decode("utf-8", "replace"))
            try: proc.stdout.close()
            except Exception: pass
            uniq = sorted(set(paths))[:limit]
            out = [p + "/" if os.path.isdir(p) else p for p in uniq]
            note = ""
            if truncated:
                note = (f"\n… (stopped at {len(out)} after {time_budget:.0f}s/{limit} cap; "
                        f"scope with a subdirectory `path` or a narrower pattern)")
            return "\n".join(out) + note
        except Exception:
            pass

    hits_l: list[str] = []                                # pruned os.walk fallback
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _PRUNE]
        for name in dirs:
            full = os.path.join(dirpath, name)
            if _match(name, os.path.relpath(full, root)):
                hits_l.append(full + "/")
        for name in files:
            full = os.path.join(dirpath, name)
            if _match(name, os.path.relpath(full, root)):
                hits_l.append(full)
        if len(hits_l) >= limit:
            return "\n".join(sorted(hits_l)[:limit]) + f"\n… (truncated at {limit}; narrow the pattern or path)"
    return "\n".join(sorted(hits_l))


def grep(workspace: Path, *, pattern: str, path: str | None = None,
         glob: str | None = None, limit: int = 500) -> str:
    """Regex content search, ripgrep-backed when available (fast; prunes heavy
    dirs; searches hidden files). `path` sets the root (default: workspace);
    use an absolute path to search anywhere. `glob` optionally filters files
    (e.g. '*.py'). Returns 'path:line:text' rows."""
    root = _root(workspace, path)
    broad = _too_broad(root)
    if broad:
        return broad
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "--line-number", "--no-heading", "--color", "never",
               "--hidden", "--max-columns", "300", "--max-count", "50"]
        for d in _PRUNE:
            cmd += ["--glob", f"!{d}"]
        if glob:
            cmd += ["--glob", glob]
        cmd += ["--", pattern, str(root)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode in (0, 1):           # 0 = matches, 1 = none
                out = res.stdout.splitlines()
                if len(out) > limit:
                    out = out[:limit] + [f"… (truncated at {limit} lines; narrow the pattern or path)"]
                return "\n".join(out)
            # returncode ≥ 2 → real error; fall through to the Python scan
        except Exception:
            pass
    # Pure-Python fallback (also pruned).
    rx = re.compile(pattern)
    out: list[str] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _PRUNE]
        for f in files:
            if glob and not fnmatch.fnmatch(f, glob):
                continue
            fp = Path(dirpath) / f
            try:
                for i, ln in enumerate(fp.read_text().splitlines()):
                    if rx.search(ln):
                        out.append(f"{fp}:{i+1}:{ln}")
                        if len(out) >= limit:
                            return "\n".join(out) + f"\n… (truncated at {limit})"
            except (UnicodeDecodeError, OSError):
                continue
    return "\n".join(out)
