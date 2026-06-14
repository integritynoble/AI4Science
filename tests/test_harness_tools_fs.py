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


def test_glob_returns_folders(tmp_path):
    (tmp_path / "low_dose_CT").mkdir()
    (tmp_path / "low_dose_CT" / "data.txt").write_text("x")
    out = fs.glob(tmp_path, pattern="*low*dose*")
    assert "low_dose_CT/" in out          # the FOLDER, suffixed with '/'


def test_glob_path_searches_outside_workspace(tmp_path):
    # workspace is empty; the data lives in a SIBLING dir reached via `path`.
    ws = tmp_path / "ws"; ws.mkdir()
    data = tmp_path / "data"; data.mkdir()
    (data / "ldct_scan.dcm").write_text("x")
    assert fs.glob(ws, pattern="*ldct*") == ""              # not under workspace
    out = fs.glob(ws, pattern="*ldct*", path=str(data))     # absolute root
    assert "ldct_scan.dcm" in out


def test_glob_prunes_heavy_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lowdose.js").write_text("x")
    (tmp_path / "real_lowdose.py").write_text("x")
    out = fs.glob(tmp_path, pattern="*lowdose*")
    assert "real_lowdose.py" in out
    assert "node_modules" not in out                        # pruned


def test_grep_path_and_glob_filter(tmp_path):
    sub = tmp_path / "proj"; sub.mkdir()
    (sub / "a.py").write_text("DOSE = 'low'\n")
    (sub / "a.md").write_text("DOSE notes\n")
    # path roots the search; glob filters to .py only
    out = fs.grep(tmp_path, pattern="DOSE", path=str(sub), glob="*.py")
    assert "a.py" in out and "a.md" not in out


def test_tool_dataclass_is_callable():
    t = Tool(name="read", description="d",
             parameters={"type": "object"}, func=fs.read, mutating=False)
    assert t.name == "read" and t.mutating is False


def test_glob_refuses_filesystem_root(tmp_path):
    # Globbing '/' would scan the whole machine and time out → instant redirect,
    # not a 20s 0-hit scan (this is what made the agent loop on glob('/')).
    out = fs.glob(tmp_path, pattern="*.py", path="/")
    assert "[refused]" in out and "too broad" in out


def test_grep_refuses_filesystem_root(tmp_path):
    out = fs.grep(tmp_path, pattern="anything", path="/")
    assert "[refused]" in out and "too broad" in out


def test_glob_normalizes_degenerate_pattern(tmp_path):
    # A bare '/' or '' pattern matches nothing under -ipath but still scans;
    # treat it as 'list everything' so the model gets results, not a 0-hit note.
    (tmp_path / "keep.py").write_text("x")
    assert "keep.py" in fs.glob(tmp_path, pattern="/")
    assert "keep.py" in fs.glob(tmp_path, pattern="")


def test_glob_allows_real_absolute_subdir(tmp_path):
    # Legit absolute paths (a real subdirectory) still work — only '/' & pseudo
    # roots are refused.
    sub = tmp_path / "data"; sub.mkdir()
    (sub / "scan.py").write_text("x")
    out = fs.glob(tmp_path, pattern="*.py", path=str(sub))
    assert "scan.py" in out and "[refused]" not in out
