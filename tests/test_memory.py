"""Tests for project-memory loading (CLAUDE.md / AI4SCIENCE.md / AGENTS.md)."""
from __future__ import annotations

from pathlib import Path

from ai4science.memory import (
    find_memory_file, load_project_memory, augment_system_prompt,
    MEMORY_FILENAMES, MAX_MEMORY_CHARS,
)


def test_no_memory_file_returns_none(tmp_path):
    assert find_memory_file(tmp_path) is None
    text, path = load_project_memory(tmp_path)
    assert text is None and path is None


def test_finds_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Project rules\nUse 4-space indent.")
    p = find_memory_file(tmp_path)
    assert p is not None and p.name == "CLAUDE.md"


def test_priority_order_claude_first(tmp_path):
    (tmp_path / "AGENTS.md").write_text("agents")
    (tmp_path / "CLAUDE.md").write_text("claude")
    # CLAUDE.md wins over AGENTS.md
    assert find_memory_file(tmp_path).name == "CLAUDE.md"


def test_ai4science_md_recognized(tmp_path):
    (tmp_path / "AI4SCIENCE.md").write_text("pwm conventions")
    assert find_memory_file(tmp_path).name == "AI4SCIENCE.md"


def test_load_returns_contents(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("always run validate before submit")
    text, path = load_project_memory(tmp_path)
    assert "validate before submit" in text
    assert path.name == "CLAUDE.md"


def test_load_truncates_huge_file(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x" * (MAX_MEMORY_CHARS + 5000))
    text, _ = load_project_memory(tmp_path)
    assert "truncated" in text.lower()
    assert len(text) <= MAX_MEMORY_CHARS + 100


def test_augment_appends_memory(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Reconstructions must be non-negative.")
    base = "You are AI4Science."
    out = augment_system_prompt(base, tmp_path)
    assert base in out
    assert "Project memory (CLAUDE.md)" in out
    assert "non-negative" in out


def test_augment_noop_without_memory(tmp_path):
    base = "You are AI4Science."
    assert augment_system_prompt(base, tmp_path) == base


def test_all_recognized_filenames_are_found(tmp_path):
    for name in MEMORY_FILENAMES:
        d = tmp_path / name.replace(".md", "")
        d.mkdir()
        (d / name).write_text("content")
        assert find_memory_file(d).name == name
