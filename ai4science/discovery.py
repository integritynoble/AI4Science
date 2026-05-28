"""Artifact discovery — classify workspace .md files by artifact_type.

Earlier versions hard-coded the four canonical filenames
(principle.md, spec.md, benchmark.md, solution.md). That blocked
multi-tier submissions, where a single spec has several benchmark
files (benchmark.md = T1, benchmark_t2.md = T2, ...).

Discovery scans every ``*.md`` in the workspace and classifies it by
the ``artifact_type`` declared in its YAML front matter. This is:

  - **backward compatible** — benchmark.md is still found
  - **forward compatible** — benchmark_t2.md, my_benchmark.md, etc. are
    found too
  - **content-based** — a README.md without front matter is ignored,
    not misclassified
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from ai4science.schemas import parse_front_matter

ARTIFACT_TYPES = ("principle", "spec", "benchmark", "solution")

# The canonical single-file names, used for "expected but absent" hints.
CANONICAL_FILES = {
    "principle": "principle.md",
    "spec": "spec.md",
    "benchmark": "benchmark.md",
    "solution": "solution.md",
}


def discover_artifacts(workspace: Path) -> Dict[str, List[Path]]:
    """Return {artifact_type: [paths]} for every .md with a recognized
    artifact_type in its front matter. Lists are sorted by filename so
    benchmark.md sorts before benchmark_t2.md."""
    workspace = workspace.resolve()
    found: Dict[str, List[Path]] = {t: [] for t in ARTIFACT_TYPES}
    for md in sorted(workspace.glob("*.md")):
        data, err = parse_front_matter(md)
        if err or not data:
            continue
        atype = data.get("artifact_type")
        if atype in found:
            found[atype].append(md)
    return found


def all_artifact_files(workspace: Path) -> List[Path]:
    """Flat, ordered list of every discovered artifact file
    (principle → spec → benchmark(s) → solution(s))."""
    found = discover_artifacts(workspace)
    ordered: List[Path] = []
    for t in ARTIFACT_TYPES:
        ordered.extend(found[t])
    return ordered


def benchmark_files(workspace: Path) -> List[Path]:
    """All benchmark .md files in the workspace (tiers), sorted by name."""
    return discover_artifacts(workspace)["benchmark"]


def resolve_benchmark(workspace: Path, name: Optional[str] = None) -> Optional[Path]:
    """Pick a benchmark file.

    - name given → that exact file (relative to workspace), if it exists
      and is a benchmark.
    - name None → benchmark.md if present, else the first discovered
      benchmark, else None.
    """
    workspace = workspace.resolve()
    benches = benchmark_files(workspace)
    if name:
        target = (workspace / name).resolve()
        for b in benches:
            if b == target:
                return b
        # Allow passing a name that exists but isn't yet classified
        # (e.g. broken front matter) so callers can surface a clear error.
        return target if target.exists() else None
    # Default: prefer the canonical benchmark.md.
    canonical = workspace / "benchmark.md"
    if canonical in benches:
        return canonical
    return benches[0] if benches else None


def missing_canonical(workspace: Path) -> List[str]:
    """Canonical artifact filenames that aren't present at all — used for
    'you may want to add X' hints, not as hard errors."""
    found = discover_artifacts(workspace)
    missing: List[str] = []
    for atype, fname in CANONICAL_FILES.items():
        if not found[atype]:
            missing.append(fname)
    return missing
