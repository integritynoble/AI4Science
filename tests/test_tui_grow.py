"""The full TUI's input is a borderless two-line prompt that grows 1→N like
Claude Code (no fixed-height box). `input_box_rows` is the pure sizing rule."""
from ai4science.harness.tui import input_box_rows


def test_empty_and_single_line_is_one_row():
    assert input_box_rows("", 80) == 1
    assert input_box_rows("hello world", 80) == 1


def test_logical_lines_grow():
    assert input_box_rows("a\nb\nc", 80) == 3


def test_trailing_newline_counts_empty_line():
    assert input_box_rows("\n", 80) == 2   # two logical lines, one empty


def test_soft_wrap_grows():
    # inner = cols-3 = 80; 200 chars → ceil(200/80) = 3 rows.
    assert input_box_rows("x" * 200, 83) == 3


def test_clamped_to_max_rows():
    big = "\n".join("x" for _ in range(50))
    assert input_box_rows(big, 80, max_rows=10) == 10
    assert input_box_rows(big, 80, max_rows=6) == 6
