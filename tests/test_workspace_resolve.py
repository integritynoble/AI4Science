"""Workspace defaults to the nearest project root; warns in $HOME."""
from pathlib import Path

from ai4science.commands.chat import _nearest_project_root, _resolve_workspace


def test_nearest_project_root_walks_up(tmp_path):
    proj = tmp_path / "proj"
    (proj / "sub" / "deep").mkdir(parents=True)
    (proj / ".git").mkdir()
    assert _nearest_project_root(proj / "sub" / "deep") == proj.resolve()


def test_nearest_project_root_none_when_no_marker(tmp_path):
    (tmp_path / "a").mkdir()
    assert _nearest_project_root(tmp_path / "a") is None


def test_resolve_uses_project_root_on_default(tmp_path):
    proj = tmp_path / "p"
    (proj / "x").mkdir(parents=True)
    (proj / "pyproject.toml").write_text("[project]\n")
    # default (cwd-equivalent) inside the project → resolves to the project root
    assert _resolve_workspace(proj / "x", was_default=True) == proj.resolve()


def test_resolve_honors_explicit_workspace(tmp_path):
    proj = tmp_path / "p"
    (proj / "x").mkdir(parents=True)
    (proj / ".git").mkdir()
    # explicit --workspace is honored as-is (not walked up)
    assert _resolve_workspace(proj / "x", was_default=False) == (proj / "x").resolve()
