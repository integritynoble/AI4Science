from ai4science.harness.diff import unified_diff
from ai4science.harness import permissions


def test_unified_diff_shows_change():
    d = unified_diff("a.py", "x = 1\ny = 2\n", "x = 42\ny = 2\n")
    assert "a.py" in d
    assert "-x = 1" in d and "+x = 42" in d
    assert " y = 2" in d


def test_unified_diff_new_file():
    d = unified_diff("new.py", "", "hello\n")
    assert "+hello" in d


def test_edit_preview_uses_diff(tmp_path):
    p = permissions._preview("edit", {"path": "a.py", "old": "x = 1", "new": "x = 42"})
    assert "-x = 1" in p and "+x = 42" in p
