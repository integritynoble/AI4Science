from pathlib import Path
from ai4science.harness.tools.base import Tool
from ai4science.harness.tools import fs


def test_read_tool(tmp_path):
    (tmp_path / "a.txt").write_text("line1\nline2\n")
    out = fs.read(tmp_path, path="a.txt")
    assert "line1" in out and "line2" in out


def test_write_then_read(tmp_path):
    fs.write(tmp_path, path="b.txt", content="hello")
    assert (tmp_path / "b.txt").read_text() == "hello"


def test_edit_replaces_unique_string(tmp_path):
    (tmp_path / "c.py").write_text("x = 1\ny = 2\n")
    fs.edit(tmp_path, path="c.py", old="x = 1", new="x = 42")
    assert (tmp_path / "c.py").read_text() == "x = 42\ny = 2\n"


def test_edit_errors_when_not_unique(tmp_path):
    (tmp_path / "d.py").write_text("a\na\n")
    try:
        fs.edit(tmp_path, path="d.py", old="a", new="b")
        assert False, "should have raised"
    except ValueError as e:
        assert "unique" in str(e).lower()


def test_glob_and_grep(tmp_path):
    (tmp_path / "x.py").write_text("import os\n")
    (tmp_path / "y.txt").write_text("nope\n")
    assert "x.py" in fs.glob(tmp_path, pattern="*.py")
    assert "x.py" in fs.grep(tmp_path, pattern="import os")


def test_tool_dataclass_is_callable():
    t = Tool(name="read", description="d",
             parameters={"type": "object"}, func=fs.read, mutating=False)
    assert t.name == "read" and t.mutating is False
