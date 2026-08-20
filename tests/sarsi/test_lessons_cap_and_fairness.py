"""Two silent failures in the lessons block: starvation, and a hidden cap.

Concatenating the trees let a long harness index fill every slot, hiding
openclaw's lessons entirely. And the block never said it had truncated, so a
partial list of what the worker knows read exactly like a complete one.
"""
import os
from pathlib import Path

import pytest

from ai4science.harness.agents.sarsi import selfaware


def _write(p: Path, lines) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Memory\n\n" + "\n".join(lines) + "\n")
    return p


def test_a_long_first_tree_does_not_starve_the_second(tmp_path):
    harness = _write(tmp_path / "h" / "MEMORY.md", [f"- harness {i}" for i in range(20)])
    openclaw = _write(tmp_path / "o" / "MEMORY.md", [f"- openclaw {i}" for i in range(20)])
    got = selfaware._lessons_from([harness, openclaw])[:8]
    assert any("openclaw" in l for l in got), "openclaw's lessons were starved"
    assert any("harness" in l for l in got), "harness's lessons were starved"


def test_the_cap_says_how_many_it_held_back(tmp_path):
    lessons = [f"- lesson {i}" for i in range(30)]
    block = selfaware._render_lessons(lessons)
    assert "22 more not shown" in block
    assert "holds all 30" in block


def test_no_notice_when_nothing_is_held_back(tmp_path):
    block = selfaware._render_lessons([f"- lesson {i}" for i in range(3)])
    assert "not shown" not in block
    assert "lesson 2" in block


def test_the_same_lesson_in_both_trees_is_counted_once(tmp_path):
    a = _write(tmp_path / "a" / "MEMORY.md", ["- shared lesson", "- only in a"])
    b = _write(tmp_path / "b" / "MEMORY.md", ["- shared lesson", "- only in b"])
    got = selfaware._lessons_from([a, b])
    assert got.count("- shared lesson") == 1
    assert "- only in a" in got and "- only in b" in got


def test_an_unreadable_tree_does_not_lose_the_other(tmp_path):
    good = _write(tmp_path / "g" / "MEMORY.md", ["- kept"])
    missing = tmp_path / "nope" / "MEMORY.md"
    assert selfaware._lessons_from([missing, good]) == ["- kept"]


def test_the_registry_free_path_also_announces_its_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    _write(tmp_path / ".openclaw" / "workspace-sarsi-worker" / "MEMORY.md",
           [f"- lesson {i}" for i in range(12)])
    out = selfaware.openclaw_workspace_context("sarsi-worker")
    assert "4 more not shown" in out
    assert "holds all 12" in out
