"""The repo must stay collectable from `pip install -e ".[dev]"` alone.

Two of this repo's test dependencies live outside it: `pwm_control_plane` is a
sibling distribution that is not on PyPI, and podman is a host service. Neither
may be needed to *import* a test module -- a module that needs one must skip.
`scripts/check-hermetic.sh` proves that from outside with a real fresh venv;
this test is the fast in-suite guard that keeps a new module from regressing
it, and it runs without a network or a second environment.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

# Distributions that `pip install -e ".[dev]"` does NOT provide. A test module
# may use them, but only behind pytest.importorskip.
OUT_OF_REPO = {"pwm_control_plane"}


def _test_modules() -> list[Path]:
    return sorted(p for p in TESTS.rglob("test_*.py"))


def _top_level_nodes(tree: ast.Module):
    """Module-level statements, in order -- what runs at import/collection."""
    return tree.body


def _importorskip_names(node: ast.stmt) -> set[str]:
    """Names guarded by a module-level pytest.importorskip("...") call."""
    names: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        if isinstance(fn, ast.Attribute) and fn.attr == "importorskip":
            if call.args and isinstance(call.args[0], ast.Constant):
                names.add(str(call.args[0].value).split(".")[0])
    return names


def _unguarded_out_of_repo_imports(path: Path) -> list[str]:
    """Out-of-repo modules imported at module level before their importorskip."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    guarded: set[str] = set()
    offenders: list[str] = []
    for node in _top_level_nodes(tree):
        imported: set[str] = set()
        if isinstance(node, ast.Import):
            imported = {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported = {node.module.split(".")[0]}
        for name in sorted(imported & OUT_OF_REPO):
            if name not in guarded:
                offenders.append(f"line {node.lineno}: {name}")
        guarded |= _importorskip_names(node)
    return offenders


def test_out_of_repo_imports_are_guarded() -> None:
    """No test module may import an out-of-repo sibling before skipping on it.

    One test rather than one per module on purpose: it adds a single item to
    the collected count, which is the number this guard exists to protect.
    """
    bad = {
        str(p.relative_to(TESTS.parent)): offenders
        for p in _test_modules()
        if (offenders := _unguarded_out_of_repo_imports(p))
    }
    assert not bad, (
        "these modules import an out-of-repo sibling at collection time, so "
        'pip install -e ".[dev]" && pytest cannot collect them: '
        f'{bad}. Put pytest.importorskip("pwm_control_plane") above the import.'
    )
