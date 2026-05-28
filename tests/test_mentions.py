"""Tests for the @-mention parser.

Covers parsing edge cases (email, abs path, traversal, trailing punctuation)
and the inline-expansion shape used by chat.py.
"""
from __future__ import annotations

from pathlib import Path

from ai4science.agents.mentions import (
    parse_mentions, expand_mentions_inline, _MENTION_RE,
)


# ─── Regex edge cases ─────────────────────────────────────────────────


def test_mention_at_start_of_line(tmp_path):
    (tmp_path / "spec.md").write_text("hi")
    assert parse_mentions("@spec.md tighten the tolerance", tmp_path) == [
        (tmp_path / "spec.md").resolve()
    ]


def test_mention_after_space(tmp_path):
    (tmp_path / "spec.md").write_text("hi")
    assert parse_mentions("please look at @spec.md", tmp_path) == [
        (tmp_path / "spec.md").resolve()
    ]


def test_email_address_does_not_match(tmp_path):
    """foo@bar.com must NOT be parsed as a mention."""
    assert parse_mentions("contact: alice@example.com about spec.md", tmp_path) == []


def test_decorator_in_prose_does_not_attach_when_no_file(tmp_path):
    """Talking about @property decorators shouldn't attach anything if no such file."""
    assert parse_mentions("the @property decorator is great", tmp_path) == []


def test_trailing_punctuation_is_stripped(tmp_path):
    (tmp_path / "spec.md").write_text("hi")
    result = parse_mentions("look at @spec.md, please", tmp_path)
    assert result == [(tmp_path / "spec.md").resolve()]


def test_multiple_mentions_preserve_order(tmp_path):
    (tmp_path / "spec.md").write_text("a")
    (tmp_path / "principle.md").write_text("b")
    result = parse_mentions("compare @principle.md and @spec.md", tmp_path)
    rels = [p.name for p in result]
    assert rels == ["principle.md", "spec.md"]


def test_duplicate_mentions_dedup(tmp_path):
    (tmp_path / "spec.md").write_text("a")
    result = parse_mentions("look at @spec.md ... @spec.md again", tmp_path)
    assert len(result) == 1


# ─── Sandbox ──────────────────────────────────────────────────────────


def test_absolute_path_is_rejected(tmp_path):
    (tmp_path / "x.txt").write_text("hi")
    # @/etc/passwd must not resolve, even if /etc/passwd exists on the system.
    assert parse_mentions("see @/etc/passwd", tmp_path) == []


def test_traversal_outside_workspace_is_rejected(tmp_path):
    # Create a file OUTSIDE the workspace but accessible via ../
    outside = tmp_path.parent / "escape.md"
    outside.write_text("outside")
    try:
        result = parse_mentions("attack @../escape.md", tmp_path)
        assert result == []
    finally:
        outside.unlink(missing_ok=True)


def test_nonexistent_file_is_skipped(tmp_path):
    """No file in workspace → no attachment (the token stays in prose)."""
    assert parse_mentions("@nonexistent.md please review", tmp_path) == []


def test_directory_is_skipped(tmp_path):
    """@code/ (directory) is not attached — we only attach files."""
    (tmp_path / "code").mkdir()
    assert parse_mentions("look in @code", tmp_path) == []


# ─── Subdirectory mentions ────────────────────────────────────────────


def test_subdirectory_mention(tmp_path):
    sub = tmp_path / "code"
    sub.mkdir()
    (sub / "run.py").write_text("print('hi')")
    result = parse_mentions("@code/run.py why does this crash?", tmp_path)
    assert result == [(sub / "run.py").resolve()]


def test_deeper_nesting(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    target = tmp_path / "a" / "b" / "c.py"
    target.write_text("hi")
    result = parse_mentions("see @a/b/c.py", tmp_path)
    assert result == [target.resolve()]


# ─── Inline expansion (used by chat.py) ───────────────────────────────


def test_expand_mentions_inline_no_mentions_unchanged(tmp_path):
    text, attached = expand_mentions_inline("just prose", tmp_path)
    assert text == "just prose"
    assert attached == []


def test_expand_mentions_inline_appends_fenced_content(tmp_path):
    f = tmp_path / "spec.md"
    f.write_text("---\nname: test spec\n---\n# body content")
    expanded, attached = expand_mentions_inline("review @spec.md", tmp_path)
    assert len(attached) == 1
    assert "review @spec.md" in expanded
    assert "Attached files (via @mention)" in expanded
    assert "test spec" in expanded
    assert "```" in expanded   # fenced


def test_expand_mentions_inline_truncates_large_files(tmp_path):
    f = tmp_path / "huge.md"
    f.write_text("x" * 20_000)
    expanded, _ = expand_mentions_inline("@huge.md", tmp_path)
    assert "truncated" in expanded.lower()


def test_expand_mentions_inline_handles_unreadable(tmp_path):
    """Binary file with invalid UTF-8 → graceful 'could not read' marker."""
    f = tmp_path / "binary.bin"
    # JPEG-like header: 0xFF is a UTF-8 continuation byte without a valid
    # multi-byte indicator — guaranteed to fail decode.
    f.write_bytes(b"\xff\xd8\xff\xe0\x80\x81\x82" * 50)
    expanded, attached = expand_mentions_inline("@binary.bin", tmp_path)
    assert len(attached) == 1
    assert "could not read" in expanded.lower()
